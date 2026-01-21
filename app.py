import streamlit as st
from supabase import create_client, Client

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

if "user_data" not in st.session_state:
    st.session_state["user_data"] = None

# --- LOGICA LOGIN ---
if st.session_state["user_data"] is None:
    st.markdown("<div class='auth-container'>", unsafe_allow_html=True)
    st.title("🏗️ BIM Login")
    with st.form("login"):
        email = st.text_input("Email").lower().strip()
        if st.form_submit_button("Accedi", use_container_width=True, type="primary"):
            res = supabase.table("user_permissions").select("*").eq("email", email).execute()
            if res.data:
                st.session_state["user_data"] = res.data[0]
                st.rerun()
            else:
                st.error("Utente non autorizzato.")
    st.markdown("</div>", unsafe_allow_html=True)
    st.stop()

# --- HOME (POST-LOGIN) ---
st.sidebar.success(f"Connesso: {st.session_state['user_data']['email']}")
if st.sidebar.button("🚪 Logout"):
    st.session_state["user_data"] = None
    st.rerun()

st.title("Welcome to BIM Data Management")
st.info("👈 Seleziona **0_📊_Project** dal menu laterale per visualizzare i dati della commessa.")
