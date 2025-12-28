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

# --- 1. NAVIGAZIONE PROGETTI ---
st.sidebar.title("🏢 Selezione Progetto")

# Recuperiamo la lista dei progetti dal DB
projects_resp = supabase.table("projects").select("id, project_name, project_code").execute()
projects_list = projects_resp.data

if not projects_list:
    st.error("Nessun progetto trovato nel database. Crea un progetto su Supabase!")
    st.stop()

# Creiamo un dizionario per il menu a tendina
project_options = {f"{p['project_code']} - {p['project_name']}": p['id'] for p in projects_list}
selected_project_label = st.sidebar.selectbox("Lavora su:", list(project_options.keys()))
project_id = project_options[selected_project_label]

st.title(f"📍 Progetto: {selected_project_label}")

# --- 2. VISUALIZZAZIONE DINAMICA ---
st.subheader("Locali e Requisiti")

# Usiamo il filtro .eq("project_id", project_id) per vedere solo i locali di quel progetto
# Selezioniamo "*" per caricare automaticamente ogni nuova colonna aggiunta su Supabase
response = supabase.table("rooms").select("*").eq("project_id", project_id).execute()
rooms_data = response.data

if rooms_data:
    st.dataframe(rooms_data, use_container_width=True)
else:
    st.info("Nessun locale inserito per questo progetto.")

# --- 3. INSERIMENTO DINAMICO ---
with st.sidebar.expander("➕ Aggiungi Locale"):
    with st.form("new_room"):
        num = st.text_input("Numero Locale")
        name = st.text_input("Nome Programmato")
        # Nota: Qui puoi aggiungere altri campi o lasciarli vuoti per aggiornarli dopo
        
        btn = st.form_submit_button("Salva")
        if btn:
            new_data = {
                "room_number": num, 
                "room_name_planned": name, 
                "project_id": project_id
            }
            supabase.table("rooms").insert(new_data).execute()
            st.success("Locale salvato!")
            st.rerun()
