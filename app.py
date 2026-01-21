import streamlit as st
from supabase import create_client, Client

# --- CONFIGURAZIONE GLOBALE ---
st.set_page_config(
    page_title="BIM Data Manager PRO", 
    layout="wide", 
    page_icon="🏗️",
    initial_sidebar_state="expanded"
)

# --- STILE CSS PERSONALIZZATO (UX ACCATTIVANTE) ---
st.markdown("""
    <style>
    .stApp { background-color: #fcfcfc; }
    .stButton>button { border-radius: 8px; font-weight: 600; }
    div[data-testid="stSidebarNav"] { padding-top: 20px; }
    .login-header { text-align: center; padding: 2rem; }
    </style>
    """, unsafe_allow_html=True)

# --- INIZIALIZZAZIONE SUPABASE ---
@st.cache_resource
def get_supabase_client():
    try:
        url = st.secrets["SUPABASE_URL"]
        key = st.secrets["SUPABASE_KEY"]
        return create_client(url, key)
    except Exception as e:
        st.error("Errore di configurazione: Controlla i Secrets di Supabase.")
        return None

supabase = get_supabase_client()

# --- GESTIONE SESSIONE ---
if "user_data" not in st.session_state:
    st.session_state["user_data"] = None

def logout():
    st.session_state["user_data"] = None
    st.rerun()

# --- INTERFACCIA DI LOGIN ---
if st.session_state["user_data"] is None:
    _, center, _ = st.columns([1, 2, 1])
    with center:
        st.markdown("<div class='login-header'><h1>🏗️ BIM Data Manager</h1><p>Versione 2.0 - Suite Professionale</p></div>", unsafe_allow_html=True)
        
        with st.container(border=True):
            email_input = st.text_input("Inserisci la tua Email Aziendale").lower().strip()
            if st.button("Accedi al Sistema", use_container_width=True, type="primary"):
                if supabase:
                    res = supabase.table("user_permissions").select("*").eq("email", email_input).execute()
                    if res.data:
                        st.session_state["user_data"] = res.data[0]
                        st.success("Accesso autorizzato!")
                        st.rerun()
                    else:
                        st.error("Utente non autorizzato. Contatta l'amministratore BIM.")
                else:
                    st.error("Connessione al database non disponibile.")
    st.stop()

# --- DASHBOARD HOME (DOPO LOGIN) ---
with st.sidebar:
    st.image("https://img.icons8.com/clouds/100/architecture.png", width=70)
    st.write(f"👤 **{st.session_state['user_data']['email']}**")
    if st.button("🚪 Esci dal sistema", use_container_width=True):
        logout()

st.title("🏗️ Benvenuto nel CDE della Commessa")
st.write("Usa il menu laterale per navigare tra i dati di progetto e le analisi BIM.")

# Card di benvenuto
st.info("💡 **Consiglio:** Vai alla pagina **'Project'** per vedere lo stato di avanzamento dei dati sincronizzati da Revit.")

c1, c2 = st.columns(2)
with c1:
    st.image("https://images.unsplash.com/photo-1503387762-592dee58c160?auto=format&fit=crop&w=800&q=80", caption="Modellazione Informativa Avanzata")
