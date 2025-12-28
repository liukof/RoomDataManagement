import streamlit as st
import pandas as pd
from supabase import create_client, Client

# --- SETUP SUPABASE ---
try:
    url = st.secrets["SUPABASE_URL"]
    key = st.secrets["SUPABASE_KEY"]
except:
    st.error("Configurazione mancante nei Secrets!")
    st.stop()

supabase: Client = create_client(url, key)

st.set_page_config(page_title="BIM Data Manager", layout="wide", page_icon="🏗️")

# --- RECUPERO PROGETTI ---
try:
    projects_resp = supabase.table("projects").select("id, project_name, project_code").execute()
    projects_list = projects_resp.data
except Exception as e:
    st.error(f"Errore di connessione: {e}")
    st.stop()

# --- BARRA DI NAVIGAZIONE ---
st.sidebar.title("🧭 Menu")
menu = st.sidebar.radio("Vai a:", ["Locali", "Mappatura Parametri", "Nuovo Progetto"])

# --- 1. PAGINA: NUOVO PROGETTO ---
if menu == "Nuovo Progetto":
    st.title("➕ Crea Nuovo Progetto")
    with st.form("form_crea_progetto", clear_on_submit=True):
        new_code = st.text_input("Codice Progetto")
        new_name = st.text_input("Nome Progetto")
        if st.form_submit_button("Crea Progetto"):
            if new_code and new_name:
                supabase.table("projects").insert({"project_code": new_code, "project_name": new_name}).execute()
                st.success("Progetto creato!")
                st.rerun()

# --- LOGICA PER LOCALI E MAPPATURA ---
elif menu in ["Locali", "Mappatura Parametri"]:
    if not projects_list:
        st.warning("Crea prima un progetto!")
        st.stop()

    st.sidebar.divider()
    project_options = {f"{p['project_code']} - {p['project_name']}": p['id'] for p in projects_list}
    selected_label = st.sidebar.selectbox("Progetto attivo:", list(project_options.keys()))
    project_id = project_options[selected_label]

    # --- 2. PAGINA: MAPPATURA PARAMETRI ---
    if menu == "Mappatura Parametri":
        st.title(f"🔗 Mappatura Parametri")
        st.caption(f"Progetto: {selected_label}")
        
        # FORM IN ALTO (Con KEY univoca per evitare l'errore)
        st.subheader("➕ Aggiungi Nuova Associazione")
        with st.form(key="form_mapping_nuovo", clear_on_submit=True):
            c1, c2 = st.columns(2)
            db_col = c1.text_input("Nome Colonna DB")
            rev_param = c2.text_input("Nome Parametro Revit")
            if st.form_submit_button("Salva Associazione"):
                if db_col and rev_param:
                    try:
                        supabase.table("parameter_mappings").insert({
                            "project_id": project_id,
                            "db_column_name": db_col,
                            "revit_parameter_name": rev_param
                        }).execute()
                        st.rerun()
                    except Exception as e:
                        st.error(f"Errore: {e}")

        st.divider()

        # VISUALIZZAZIONE IN BASSO
        st.subheader("Configurazione Attiva")
        maps_resp = supabase.table("parameter_mappings").select("*").eq("project_id", project_id).execute()
        if maps_resp.data:
            df_map = pd.DataFrame(maps_resp.data)
            st.dataframe(df_map[["db_column_name", "revit_parameter_name"]], use_container_width=True, hide_index=True)
            if st.button("🗑️ Reset Mappature"):
                supabase.table("parameter_mappings").delete().eq("project_id", project_id).execute()
                st.rerun()
        else:
            st.info("Nessuna mappatura.")

    # --- 3. PAGINA: LOCALI ---
    elif menu == "Locali":
        st.title(f"📍 Gestione Locali")
        st.caption(f"Progetto: {selected_label}")
        
        res = supabase.table("rooms").select("*").eq("project_id", project_id).execute()
        if res.data:
            st.dataframe(res.data, use_container_width=True)
        
        with st.sidebar.expander("➕ Aggiungi Locale"):
            with st.form(key="form_locale_nuovo", clear_on_submit=True):
                num = st.text_input("Numero")
                nam = st.text_input("Nome")
                if st.form_submit_button("Salva"):
                    supabase.table("rooms").insert({"room_number": num, "room_name_planned": nam, "project_id": project_id}).execute()
                    st.rerun()
