import streamlit as st
from supabase import create_client, Client
import extra_streamlit_components as stx
from datetime import datetime, timedelta

# --- CONFIGURAZIONE ---
st.set_page_config(page_title="BIM Data Manager PRO", layout="wide", page_icon="🏗️")

# CSS per UI Professionale
st.markdown("""
    <style>
    .main { background-color: #f9f9fb; }
    .stButton>button { border-radius: 6px; }
    .auth-container { max-width: 400px; margin: auto; padding-top: 5rem; }
    </style>
    """, unsafe_allow_html=True)

@st.cache_resource
def get_supabase():
    return create_client(st.secrets["SUPABASE_URL"], st.secrets["SUPABASE_KEY"])

supabase = get_supabase()

# Inizializzazione cookie manager
cookie_manager = stx.CookieManager()

if "user_data" not in st.session_state:
    st.session_state["user_data"] = None

# --- LOGICA AUTO-LOGIN (COOKIE) ---
saved_email = cookie_manager.get(cookie="user_email")

if st.session_state["user_data"] is None and saved_email:
    # Tentativo di login automatico se abbiamo il cookie
    res = supabase.table("user_permissions").select("*").eq("email", saved_email).execute()
    if res.data:
        st.session_state["user_data"] = res.data[0]
        st.rerun()

# --- LOGICA LOGIN ---
if st.session_state["user_data"] is None:
    st.markdown("<div class='auth-container'>", unsafe_allow_html=True)
    st.title("🏗️ BIM Login")
    with st.form("login"):
        email = st.text_input("Email").lower().strip()
        remember_me = st.checkbox("Ricordami su questo browser", value=True)
        if st.form_submit_button("Accedi", use_container_width=True, type="primary"):
            res = supabase.table("user_permissions").select("*").eq("email", email).execute()
            if res.data:
                st.session_state["user_data"] = res.data[0]
                if remember_me:
                    # Salva cookie per 30 giorni
                    cookie_manager.set("user_email", email, expires_at=datetime.now() + timedelta(days=30))
                st.rerun()
            else:
                st.error("Utente non autorizzato.")
    st.markdown("</div>", unsafe_allow_html=True)
    st.stop()

# --- HOME (POST-LOGIN) ---
st.sidebar.success(f"Connesso: {st.session_state['user_data']['email']}")
if st.sidebar.button("🚪 Logout"):
    st.session_state["user_data"] = None
    cookie_manager.delete("user_email") # Rimuove anche il cookie al logout
    st.rerun()

st.title("Welcome to BIM Data Management")
st.info("👈 Seleziona una pagina dal menu laterale per iniziare.")
