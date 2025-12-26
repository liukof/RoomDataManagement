import streamlit as st
from supabase import create_client, Client

# 1. Recupero sicuro delle credenziali
# In Streamlit Cloud le imposterai nel menu "Secrets"
try:
    url = st.secrets["SUPABASE_URL"]
    key = st.secrets["SUPABASE_KEY"]
except:
    st.error("Configurazione mancante! Imposta SUPABASE_URL e SUPABASE_KEY nei Secrets di Streamlit.")
    st.stop()

supabase: Client = create_client(url, key)

st.set_page_config(page_title="BIM Room Manager", layout="wide")

st.title("🏗️ Gestione Informativa Locali")
st.sidebar.info("Sincronizzato con il database Supabase della società.")

# --- SEZIONE VISUALIZZAZIONE ---
st.subheader("Locali Pianificati")

# Recuperiamo i dati dalla tabella 'rooms' che hai creato con lo script SQL
response = supabase.table("rooms").select("id, room_number, room_name_planned, department, revit_guid").execute()
data = response.data

if data:
    # Mostriamo una tabella interattiva
    st.dataframe(data, use_container_width=True)
else:
    st.warning("Nessun locale presente nel database.")

# --- SEZIONE INSERIMENTO ---
with st.sidebar:
    st.header("➕ Nuovo Locale")
    with st.form("form_nuovo_locale"):
        num = st.text_input("Numero Locale (es. 101)")
        name = st.text_input("Nome Locale (es. Ufficio)")
        dept = st.selectbox("Dipartimento", ["Amministrazione", "Tecnico", "Produzione", "Logistica"])
        # Supponiamo di avere già un progetto con ID 1 per i test
        btn = st.form_submit_button("Aggiungi al DB")
        
        if btn:
            nuovo_locale = {
                "room_number": num,
                "room_name_planned": name,
                "department": dept,
                "project_id": 1 # Assicurati di aver creato almeno un progetto nella tabella 'projects'
            }
            try:
                supabase.table("rooms").insert(nuovo_locale).execute()
                st.success(f"Locale {num} aggiunto correttamente!")
                st.rerun()
            except Exception as e:
                st.error(f"Errore: {e}")