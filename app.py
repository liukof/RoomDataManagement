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

# --- BARRA DI NAVIGAZIONE ---
menu = st.sidebar.radio("Naviga", ["Rooms", "New Project"])

# --- PAGINA: NUOVO PROGETTO ---
if menu == "New Project":
    st.title("➕ New Project")
    with st.form("create_project"):
        new_code = st.text_input("Code Project (es. PRJ-002)")
        new_name = st.text_input("Name Project (es. Scuola Primaria)")
        submit_prj = st.form_submit_button("Create Project")
        
        if submit_prj:
            if new_code and new_name:
                try:
                    data = {"project_code": new_code, "project_name": new_name}
                    supabase.table("projects").insert(data).execute()
                    st.success(f"Project '{new_name}' created!")
                    st.balloons()
                except Exception as e:
                    st.error(f"Errore: {e}")
            else:
                st.warning("Compile all the fields.")

# --- PAGINA: LOCALI ---
elif menu == "Rooms":
    st.sidebar.title("🏢 Select Project")
    
    # Recuperiamo la lista dei progetti
    projects_resp = supabase.table("projects").select("id, project_name, project_code").execute()
    projects_list = projects_resp.data

    if not projects_list:
        st.warning("Nessun progetto trovato. Vai su 'Nuovo Progetto' per iniziare.")
        st.stop()

    project_options = {f"{p['project_code']} - {p['project_name']}": p['id'] for p in projects_list}
    selected_project_label = st.sidebar.selectbox("Work on:", list(project_options.keys()))
    project_id = project_options[selected_project_label]

    st.title(f"📍 Project: {selected_project_label}")

    # Visualizzazione Locali (Dinamicamente con "*")
    response = supabase.table("rooms").select("*").eq("project_id", project_id).execute()
    rooms_data = response.data

    if rooms_data:
        st.dataframe(rooms_data, use_container_width=True)
    else:
        st.info("Nessun locale inserito per questo progetto.")

    # Inserimento Locale
    with st.sidebar.expander("➕ Aggiungi Locale"):
        with st.form("new_room"):
            num = st.text_input("Numero Locale")
            name = st.text_input("Nome Programmato")
            btn = st.form_submit_button("Salva")
            if btn:
                new_data = {"room_number": num, "room_name_planned": name, "project_id": project_id}
                supabase.table("rooms").insert(new_data).execute()
                st.success("Locale salvato!")
                st.rerun()


