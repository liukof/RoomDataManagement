import streamlit as st
import pandas as pd
from supabase import create_client, Client

# --- SETUP SUPABASE ---
try:
    url = st.secrets["SUPABASE_URL"]
    key = st.secrets["SUPABASE_KEY"]
except:
    st.error("Configurazione mancante nei Secrets di Streamlit! Carica SUPABASE_URL e SUPABASE_KEY.")
    st.stop()

supabase: Client = create_client(url, key)

st.set_page_config(page_title="BIM Data Manager", layout="wide", page_icon="🏗️")

# --- RECUPERO PROGETTI (Necessario per tutte le pagine) ---
try:
    projects_resp = supabase.table("projects").select("id, project_name, project_code").execute()
    projects_list = projects_resp.data
except Exception as e:
    st.error(f"Errore di connessione al database: {e}")
    st.stop()

# --- BARRA DI NAVIGAZIONE LATERALE ---
st.sidebar.title("🧭 Menu")
menu = st.sidebar.radio("Vai a:", ["Locali", "Mappatura Parametri", "Nuovo Progetto"])

# --- 1. PAGINA: NUOVO PROGETTO ---
if menu == "Nuovo Progetto":
    st.title("➕ Crea Nuovo Progetto")
    st.info("Configura una nuova commessa nel database centrale.")
    
    with st.form("create_project", clear_on_submit=True):
        new_code = st.text_input("Codice Progetto (es. PRJ-2024-01)")
        new_name = st.text_input("Nome Progetto (es. Nuovo Ospedale)")
        submit_prj = st.form_submit_button("Crea Progetto")
        
        if submit_prj:
            if new_code and new_name:
                try:
                    data = {"project_code": new_code, "project_name": new_name}
                    supabase.table("projects").insert(data).execute()
                    st.success(f"Progetto '{new_name}' registrato correttamente!")
                    st.balloons()
                    st.rerun()
                except Exception as e:
                    st.error(f"Errore durante il salvataggio: {e}")
            else:
                st.warning("Assicurati di inserire sia il codice che il nome.")

# --- LOGICA COMUNE PER LOCALI E MAPPATURA (Richiedono un progetto selezionato) ---
elif menu in ["Locali", "Mappatura Parametri"]:
    if not projects_list:
        st.warning("Nessun progetto trovato. Crea il tuo primo progetto nella sezione 'Nuovo Progetto'.")
        st.stop()

    st.sidebar.divider()
    st.sidebar.title("🏢 Seleziona Commessa")
    project_options = {f"{p['project_code']} - {p['project_name']}": p['id'] for p in projects_list}
    selected_project_label = st.sidebar.selectbox("Lavora su:", list(project_options.keys()))
    project_id = project_options[selected_project_label]

    # --- 2. PAGINA: MAPPATURA PARAMETRI ---
    if menu == "Mappatura Parametri":
        st.title(f"🔗 Mappatura Parametri")
        st.caption(f"Progetto Attivo: {selected_project_label}")
        
        # --- Visualizzazione Tabella Mappature ---
        st.subheader("Configurazione Attiva")
        maps_resp = supabase.table("parameter_mappings").select("*").eq("project_id", project_id).execute()
        
        if maps_resp.data:
            df_map = pd.DataFrame(maps_resp.data)
            # Pulizia e rinomina per l'utente
            df_display = df_map[["db_column_name", "revit_parameter_name"]].rename(columns={
                "db_column_name": "Colonna Database (Supabase)",
                "revit_parameter_name": "Parametro Revit Target"
            })
            st.dataframe(df_display, use_container_width=True, hide_index=True)
            
            if st.button("🗑️ Reset Mappature Progetto"):
                supabase.table("parameter_mappings").delete().eq("project_id", project_id).execute()
                st.rerun()
        else:
            st.info("Nessuna mappatura trovata. Definisci come i dati del DB devono popolare Revit.")

        st.divider()

        # --- Form Inserimento Mappatura ---
        st.subheader("➕ Aggiungi Nuova Associazione")
        with st.form("new_mapping", clear_on_submit=True):
            c1, c2 = st.columns(2)
            db_col = c1.text_input("Nome Colonna DB", placeholder="es: Comments")
            revit_param = c2.text_input("Nome Parametro Revit", placeholder="es: Commenti")
            
            if st.form_submit_button("Salva Associazione"):
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
                        st.error(f"Errore: {e}")

    # --- 3. PAGINA: LOCALI ---
    elif menu == "Locali":
        st.title(f"📍 Gestione Locali")
        st.caption(f"Progetto Attivo: {selected_project_label}")

        # Recupero dati dinamico (*)
        response = supabase.table("rooms").select("*").eq("project_id", project_id).execute()
        
        if response.data:
            st.dataframe(response.data, use_container_width=True)
        else:
            st.info("Il database locale per questo progetto è vuoto.")

        # Sidebar per aggiunta rapida locale
        with st.sidebar.expander("➕ Aggiungi Locale"):
            with st.form("new_room", clear_on_submit=True):
                num = st.text_input("Numero Locale")
                name = st.text_input("Nome Programmato")
                if st.form_submit_button("Salva nel DB"):
                    if num and name:
                        new_data = {
                            "room_number": num, 
                            "room_name_planned": name, 
                            "project_id": project_id
                        }
                        supabase.table("rooms").insert(new_data).execute()
                        st.rerun()
                    else:
                        st.error("Inserisci Numero e Nome.")
