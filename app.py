import streamlit as st
from supabase import create_client, Client

# --- CONFIGURAZIONE E STILE ---
st.set_page_config(page_title="BIM Data Manager PRO", layout="wide", page_icon="🏗️")

# CSS per rendere la UI più moderna (UX Accattivante)
st.markdown("""
    <style>
    /* Gradient per l'header */
    .main {
        background: #f8f9fa;
    }
    .stButton>button {
        border-radius: 5px;
        height: 3em;
        transition: all 0.3s;
    }
    .stButton>button:hover {
        border-color: #007bff;
        color: #007bff;
    }
    /* Card per i KPI */
    div[data-testid="stMetricValue"] {
        font-size: 1.8rem;
        color: #0e1117;
    }
    </style>
    """, unsafe_allow_html=True)

@st.cache_resource
def get_client():
    url = st.secrets["SUPABASE_URL"]
    key = st.secrets["SUPABASE_KEY"]
    return create_client(url, key)

supabase = get_client()

# --- LOGICA DI SESSIONE ---
if "user_data" not in st.session_state:
    st.session_state["user_data"] = None

# --- PAGINA DI LOGIN ---
if st.session_state["user_data"] is None:
    left_co, cent_co, last_co = st.columns([1,2,1])
    with cent_co:
        st.markdown("<h1 style='text-align: center;'>🏗️</h1>", unsafe_allow_html=True)
        st.markdown("<h2 style='text-align: center;'>BIM Data Manager PRO</h2>", unsafe_allow_html=True)
        
        with st.container(border=True):
            email_input = st.text_input("Email Aziendale").lower().strip()
            if st.button("Accedi al Sistema", use_container_width=True, type="primary"):
                res = supabase.table("user_permissions").select("*").eq("email", email_input).execute()
                if res.data:
                    st.session_state["user_data"] = res.data[0]
                    st.rerun()
                else:
                    st.error("Accesso negato. Utente non autorizzato.")
    st.stop()

# --- DASHBOARD POST-LOGIN ---
current_user = st.session_state["user_data"]

# Sidebar migliorata
with st.sidebar:
    st.image("https://img.icons8.com/clouds/100/architecture.png", width=80)
    st.markdown(f"**Utente:** `{current_user['email']}`")
    st.caption(f"Ruolo: {current_user.get('role', 'Standard User')}")
    if st.button("🚪 Esci", use_container_width=True):
        st.session_state["user_data"] = None
        st.rerun()

# --- CONTENUTO PRINCIPALE ---
st.title("📊 Dashboard di Progetto")

# Esempio di KPI (Dati fittizi, da collegare alle tue tabelle Supabase)
# 
col1, col2, col3, col4 = st.columns(4)

with col1:
    st.metric(label="Locali Totali", value="145", delta="+3 questa settimana")
with col2:
    st.metric(label="Superficie Totale", value="2,450 m²")
with col3:
    st.metric(label="Parametri Compilati", value="88%", delta="5%")
with col4:
    st.metric(label="Errori di Sync", value="0", delta_color="normal")

st.divider()

# Griglia di navigazione rapida
st.subheader("Azioni Rapide")
c1, c2 = st.columns(2)
with c1:
    with st.expander("📝 Gestione Locali", expanded=True):
        st.write("Visualizza ed edita i parametri delle stanze dal database.")
        if st.button("Vai ai Locali", key="go_rooms"):
            st.info("Naviga tramite il menu laterale a '01_Room_Data'")
with c2:
    with st.expander("📂 Importazione Dati", expanded=True):
        st.write("Carica nuovi file CSV o Excel estratti da Revit.")
        if st.button("Vai a Import", key="go_import"):
            st.info("Naviga tramite il menu laterale a '02_Import'")
