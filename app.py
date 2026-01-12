import streamlit as st
from supabase import create_client, Client

# Configurazione Iniziale
st.set_page_config(page_title="BIM Data Manager PRO", layout="wide", page_icon="🏗️")

# Inizializzazione Supabase (Accessibile a tutti i moduli)
@st.cache_resource
def get_client():
    url = st.secrets["SUPABASE_URL"]
    key = st.secrets["SUPABASE_KEY"]
    return create_client(url, key)

supabase = get_client()

# --- GESTIONE SESSIONE ---
if "user_data" not in st.session_state:
    st.session_state["user_data"] = None

def logout():
    st.session_state["user_data"] = None
    st.rerun()

# --- LOGIC DI LOGIN ---
if st.session_state["user_data"] is None:
    st.title("🏗️ BIM Data Manager - Login")
    with st.form("login_form"):
        email_input = st.text_input("Email Address").lower().strip()
        if st.form_submit_button("Login", use_container_width=True, type="primary"):
            res = supabase.table("user_permissions").select("*").eq("email", email_input).execute()
            if res.data:
                st.session_state["user_data"] = res.data[0]
                st.rerun()
            else:
                st.error("User not authorized.")
    st.stop()

# --- HOME PAGE (DOPO LOGIN) ---
current_user = st.session_state["user_data"]
st.sidebar.write(f"👤 **{current_user['email']}**")
if st.sidebar.button("🚪 Logout"):
    logout()

st.title("🏗️ Dashboard Principale")
st.write(f"Benvenuto nel gestore dati BIM. Usa il menu a sinistra per navigare tra le sezioni.")

# Messaggio di aiuto per i nuovi utenti
st.info("👈 Seleziona una scheda dal menu laterale per gestire Locali, Catalogo o Parametri.")
