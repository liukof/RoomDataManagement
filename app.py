import streamlit as st
from supabase import create_client, Client

# --- SETUP SUPABASE ---
try:
    url = st.secrets["SUPABASE_URL"]
    key = st.secrets["SUPABASE_KEY"]
except:
    st.error("Configurazione mancante nei Secrets!")
    st.stop()

supabase: Client = create_client(url, key)

st.set_page_config(page_title="BIM Data Manager", layout="wide")

# --- RECUPERO PROGETTI (Sempre necessario) ---
projects_resp = supabase.table("projects").select("id, project_name, project_code").execute()
projects_list = projects_resp.data

# --- BARRA DI NAVIGAZIONE ---
menu = st.sidebar.radio("Naviga", ["Locali", "Mappatura Parametri", "Nuovo Progetto"])

# --- PAGINA: NUOVO PROGETTO ---
if menu == "Nuovo Progetto":
    st.title("➕ Crea Nuovo Progetto")
    with st.form("create_project"):
        new_code = st.text_input("Codice Progetto (es. PRJ-002)")
        new_name = st.text_input("Nome Progetto (es. Scuola Primaria)")
        submit_prj = st.form_submit_button("Crea Progetto")
        
        if submit_prj:
            if new_code and new_name:
                try:
                    data = {"project_code": new_code, "project_name": new_name}
                    supabase.table("projects").insert(data).execute()
                    st.success(f"Progetto '{new_name}' creato!")
                    st.rerun()
                except Exception as e:
                    st.error(f"Errore: {e}")

# --- LOGICA COMUNE PER LOCALI E MAPPATURA ---
elif menu in ["Locali", "Mappatura Parametri"]:
    if not projects_list:
        st.warning("Crea prima un progetto!")
        st.stop()

    project_options = {f"{p['project_code']} - {p['project_name']}": p['id'] for p in projects_list}
    selected_project_label = st.sidebar.selectbox("Progetto attivo:", list(project_options.keys()))
    project_id = project_options[selected_project_label]

    # --- PAGINA: MAPPATURA PARAMETRI ---
    if menu == "Mappatura Parametri":
        st.title(f"🔗 Mappatura Parametri - {selected_project_label}")
        
        # 1. Visualizza mappature esistenti
        maps_resp = supabase.table("parameter_mappings").select("*").eq("project_id", project_id).execute()
        if maps_resp.data:
            st.write("Mappature attive:")
            st.table(maps_resp.data)
        
        # 2. Form per nuova mappatura
        st.subheader("Aggiungi Nuova Associazione")
        with st.form("new_mapping"):
            col1, col2 = st.columns(2)
            with col1:
                db_col = st.text_input("Nome Colonna DB (es: Comments o floor_material)")
            with col2:
                revit_param = st.text_input("Nome Parametro Revit (es: Commenti o Finitura_Pavimento)")
            
            submit_map = st.form_submit_button("Salva Mappatura")
            
            if submit_map:
                if db_col and revit_param:
                    try:
                        map_data = {
                            "project_id": project_id,
                            "db_column_name": db_col,
                            "revit_parameter_name": revit_param
                        }
                        supabase.table("parameter_mappings").insert(map_data).execute()
                        st.success("Mappatura salvata!")
                        st.rerun()
                    except Exception as e:
                        st.error(f"Errore (controlla se la colonna esiste nel DB): {e}")

    # --- PAGINA: LOCALI ---
    elif menu == "Locali":
        st.title(f"📍 Gestione Locali - {selected_project_label}")
        
        # Carichiamo i locali (con tutte le colonne)
        response = supabase.table("rooms").select("*").eq("project_id", project_id).execute()
        if response.data:
            st.dataframe(response.data, use_container_width=True)
        else:
            st.info("Nessun locale trovato.")

        with st.sidebar.expander("➕ Aggiungi Locale"):
            with st.form("new_room"):
                num = st.text_input("Numero Locale")
                name = st.text_input("Nome Programmato")
                btn = st.form_submit_button("Salva")
                if btn:
                    new_data = {"room_number": num, "room_name_planned": name, "project_id": project_id}
                    supabase.table("rooms").insert(new_data).execute()
                    st.rerun()
