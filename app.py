import streamlit as st
import pandas as pd
from supabase import create_client, Client
import io

# --- SETUP SUPABASE ---
try:
    url = st.secrets["SUPABASE_URL"]
    key = st.secrets["SUPABASE_KEY"]
except:
    st.error("Configurazione mancante nei Secrets! Carica SUPABASE_URL e SUPABASE_KEY.")
    st.stop()

supabase: Client = create_client(url, key)

st.set_page_config(page_title="BIM Data Manager", layout="wide", page_icon="🏗️")

# --- RECUPERO PROGETTI ---
try:
    projects_resp = supabase.table("projects").select("id, project_name, project_code").execute()
    projects_list = projects_resp.data
except Exception as e:
    st.error(f"Errore di connessione al database: {e}")
    st.stop()

# --- BARRA DI NAVIGAZIONE ---
st.sidebar.title("🧭 Menu")
menu = st.sidebar.radio("Vai a:", ["Locali", "Mappatura Parametri", "Nuovo Progetto"])

# --- LOGICA PER LOCALI E MAPPATURA ---
if menu in ["Locali", "Mappatura Parametri"]:
    if not projects_list:
        st.sidebar.warning("Crea prima un progetto per iniziare.")
        st.stop()

    st.sidebar.divider()
    project_options = {f"{p['project_code']} - {p['project_name']}": p for p in projects_list}
    selected_label = st.sidebar.selectbox("Progetto attivo:", list(project_options.keys()))
    selected_project = project_options[selected_label]
    project_id = selected_project['id']

    # --- HEADER AREA PRINCIPALE (CON GESTIONE A DESTRA) ---
    col_titolo, col_gestione = st.columns([3, 1])
    
    with col_titolo:
        st.title(f"{'📍' if menu == 'Locali' else '🔗'} {menu}")
        st.write(f"Commessa: **{selected_label}**")
    
    with col_gestione:
        st.write("###") # Allineamento verticale
        with st.expander("⚙️ Gestisci Progetto", expanded=False):
            st.subheader("Modifica Dati")
            edit_code = st.text_input("Codice Progetto", value=selected_project['project_code'], key="edit_code")
            edit_name = st.text_input("Nome Progetto", value=selected_project['project_name'], key="edit_name")
            
            if st.button("💾 Salva Modifiche"):
                supabase.table("projects").update({
                    "project_code": edit_code, "project_name": edit_name
                }).eq("id", project_id).execute()
                st.toast("Progetto aggiornato!")
                st.rerun()

            st.divider()
            st.subheader("🗑️ Elimina")
            confirm_del = st.text_input("Scrivi 'ELIMINA' per confermare:")
            if st.button("🔥 Elimina Definitivamente"):
                if confirm_del == "ELIMINA":
                    supabase.table("projects").delete().eq("id", project_id).execute()
                    st.rerun()
                else:
                    st.warning("Conferma non corretta.")

    st.divider()

    # --- 2. PAGINA: MAPPATURA PARAMETRI ---
    if menu == "Mappatura Parametri":
        # --- SEZIONE IMPORTAZIONE EXCEL (RIPRISTINATA) ---
        with st.expander("📥 Importazione Massiva (Excel/CSV)"):
            st.write("Scarica il template, compilalo e caricalo per mappare i parametri Revit.")
            
            template_df = pd.DataFrame(columns=["Database", "Revit"])
            buffer = io.BytesIO()
            with pd.ExcelWriter(buffer, engine='xlsxwriter') as writer:
                template_df.to_excel(writer, index=False, sheet_name='Mappatura')
            
            st.download_button(
                label="⬇️ Scarica Template Excel",
                data=buffer.getvalue(),
                file_name="template_mappatura.xlsx",
                mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
            )
            
            uploaded_file = st.file_uploader("Carica file compilato", type=["xlsx", "csv"])
            if uploaded_file:
                try:
                    df_import = pd.read_excel(uploaded_file) if uploaded_file.name.endswith('.xlsx') else pd.read_csv(uploaded_file)
                    df_import = df_import.dropna(how='all')
                    
                    if all(col in df_import.columns for col in ["Database", "Revit"]):
                        st.write("Anteprima dati rilevati:")
                        st.dataframe(df_import, height=180, hide_index=True)
                        
                        if st.button("🚀 Conferma Importazione"):
                            df_valid = df_import.dropna(subset=["Database", "Revit"])
                            batch = [
                                {
                                    "project_id": project_id,
                                    "db_column_name": str(row['Database']).strip(),
                                    "revit_parameter_name": str(row['Revit']).strip()
                                } for _, row in df_valid.iterrows()
                            ]
                            if batch:
                                supabase.table("parameter_mappings").insert(batch).execute()
                                st.success(f"Importate {len(batch)} associazioni!")
                                st.rerun()
                    else:
                        st.error("Il file deve contenere le colonne 'Database' e 'Revit'")
                except Exception as e:
                    st.error(f"Errore: {e}")

        # --- INSERIMENTO SINGOLO ---
        st.subheader("➕ Aggiungi Singola Associazione")
        with st.form(key="form_mapping_single", clear_on_submit=True):
            c1, c2 = st.columns(2)
            db_col = c1.text_input("Colonna Database (es. Comments)")
            rev_param = c2.text_input("Parametro Revit (es. Commenti)")
            if st.form_submit_button("Salva"):
                if db_col and rev_param:
                    supabase.table("parameter_mappings").insert({
                        "project_id": project_id,
                        "db_column_name": db_col,
                        "revit_parameter_name": rev_param
                    }).execute()
                    st.rerun()

        # --- VISUALIZZAZIONE LISTA ---
        st.subheader("📋 Configurazione Attiva")
        maps_resp = supabase.table("parameter_mappings").select("*").eq("project_id", project_id).execute()
        if maps_resp.data:
            df_active = pd.DataFrame(maps_resp.data)
            st.dataframe(df_active[["db_column_name", "revit_parameter_name"]].rename(columns={
                "db_column_name": "Database", "revit_parameter_name": "Revit"
            }), use_container_width=True, hide_index=True)
            
            if st.button("🗑️ Reset Mappature"):
                supabase.table("parameter_mappings").delete().eq("project_id", project_id).execute()
                st.rerun()
        else:
            st.info("Nessuna mappatura definita per questo progetto.")

    # --- 3. PAGINA: LOCALI ---
    elif menu == "Locali":
        rooms_resp = supabase.table("rooms").select("*").eq("project_id", project_id).execute()
        if rooms_resp.data:
            st.dataframe(rooms_resp.data, use_container_width=True)
        else:
            st.info("Nessun locale presente nel database per questo progetto.")

        with st.sidebar.expander("➕ Inserimento Rapido Locale"):
            with st.form(key="form_fast_room", clear_on_submit=True):
                num = st.text_input("Numero Locale")
                nam = st.text_input("Nome Programmato")
                if st.form_submit_button("Aggiungi"):
                    if num and nam:
                        supabase.table("rooms").insert({
                            "room_number": num,
                            "room_name_planned": nam,
                            "project_id": project_id
                        }).execute()
                        st.rerun()

# --- 1. PAGINA: NUOVO PROGETTO ---
elif menu == "Nuovo Progetto":
    st.title("➕ Crea Nuovo Progetto")
    with st.form("form_crea_progetto", clear_on_submit=True):
        new_code = st.text_input("Codice Progetto (es. PRJ-2025-01)")
        new_name = st.text_input("Nome Progetto (es. Scuola Primaria)")
        if st.form_submit_button("Crea Progetto"):
            if new_code and new_name:
                try:
                    supabase.table("projects").insert({"project_code": new_code, "project_name": new_name}).execute()
                    st.success("Progetto registrato!")
                    st.rerun()
                except Exception as e:
                    st.error(f"Errore: {e}")
