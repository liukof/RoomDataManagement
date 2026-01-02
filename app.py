import streamlit as st
import pandas as pd
from supabase import create_client, Client
import io

# --- SETUP SUPABASE E ADMIN PWD ---
try:
    url = st.secrets["SUPABASE_URL"]
    key = st.secrets["SUPABASE_KEY"]
    admin_pwd = st.secrets["ADMIN_PASSWORD"] # La tua password master
except:
    st.error("Configurazione mancante nei Secrets (SUPABASE_URL, SUPABASE_KEY, ADMIN_PASSWORD)!")
    st.stop()

supabase: Client = create_client(url, key)

st.set_page_config(page_title="BIM Data Manager PRO", layout="wide", page_icon="🏗️")

# --- RECUPERO PROGETTI ---
try:
    projects_resp = supabase.table("projects").select("*").order("project_code").execute()
    projects_list = projects_resp.data
except Exception as e:
    st.error(f"Errore di connessione: {e}")
    st.stop()

# --- BARRA DI NAVIGAZIONE ---
st.sidebar.title("🏗️ BIM Data Manager")
menu = st.sidebar.radio("Vai a:", ["Locali", "Mappatura Parametri", "Gestione Progetti"])

# --- LOGICA DI ACCESSO PROGETTI (PER COLLABORATORI) ---
if menu in ["Locali", "Mappatura Parametri"]:
    if not projects_list:
        st.sidebar.warning("Nessun progetto disponibile.")
        st.stop()

    st.sidebar.divider()
    project_options = {f"{p['project_code']} - {p['project_name']}": p for p in projects_list}
    selected_label = st.sidebar.selectbox("Seleziona Progetto:", list(project_options.keys()))
    project_data = project_options[selected_label]
    project_id = project_data['id']
    auth_key = f"auth_{project_id}"

    if auth_key not in st.session_state or not st.session_state[auth_key]:
        st.title("🔒 Accesso Progetto Protetto")
        st.info(f"Il progetto **{selected_label}** richiede una chiave di accesso specifica.")
        with st.container():
            col_a, col_b, col_c = st.columns([1, 2, 1])
            with col_b:
                with st.form("login_gate"):
                    pwd_input = st.text_input("Password Progetto", type="password")
                    if st.form_submit_button("Sblocca Progetto", use_container_width=True):
                        if pwd_input == project_data.get('project_password'):
                            st.session_state[auth_key] = True
                            st.rerun()
                        else:
                            st.error("Password errata.")
        st.stop()

    # --- CONTENUTO PAGINE LOCALI/MAPPE (SOLO SE AUTENTICATI) ---
    st.title(f"{menu}")
    st.caption(f"Progetto: {selected_label}")
    
    if menu == "Locali":
        # (Logica editor locali invariata come sopra...)
        maps_resp = supabase.table("parameter_mappings").select("db_column_name").eq("project_id", project_id).execute()
        mapped_params = [m['db_column_name'] for m in maps_resp.data]
        
        with st.expander("📥 Import / Export / Reset"):
            c1, c2, c3 = st.columns(3)
            with c1:
                rooms_raw = supabase.table("rooms").select("*").eq("project_id", project_id).order("room_number").execute()
                df_exp = pd.DataFrame(rooms_raw.data) # Logica semplificata per brevità
                st.download_button("⬇️ Scarica Excel", data=io.BytesIO().getvalue(), file_name="export.xlsx") # Esempio
            # ... resto della logica import/export/editor ...
            st.info("Logica editor attiva. (Incolla qui la parte dell'editor precedentemente fornita)")

# --- LOGICA AREA ADMIN (SOLO PER TE) ---
elif menu == "Gestione Progetti":
    st.title("🛡️ Area Amministratore")
    
    if "admin_auth" not in st.session_state or not st.session_state["admin_auth"]:
        st.warning("Questa sezione è riservata al proprietario della Web App.")
        with st.container():
            col_a, col_b, col_c = st.columns([1, 1, 1])
            with col_b:
                with st.form("admin_login"):
                    master_pwd = st.text_input("Inserisci Password MASTER", type="password")
                    if st.form_submit_button("Accedi come Admin", use_container_width=True):
                        if master_pwd == admin_pwd:
                            st.session_state["admin_auth"] = True
                            st.rerun()
                        else:
                            st.error("Password Master errata.")
        st.stop()

    # --- SE SEI ADMIN, VEDI TUTTO ---
    st.success("Accesso Admin Verificato")
    if st.button("Esci da Area Admin"):
        st.session_state["admin_auth"] = False
        st.rerun()

    t1, t2 = st.tabs(["➕ Crea Nuovo Progetto", "📝 Gestisci/Vedi Password"])
    
    with t1:
        with st.form("new_prj_admin"):
            cp = st.text_input("Codice")
            np = st.text_input("Nome")
            pw = st.text_input("Password da assegnare ai collaboratori")
            if st.form_submit_button("Crea"):
                supabase.table("projects").insert({"project_code": cp, "project_name": np, "project_password": pw}).execute()
                st.rerun()

    with t2:
        if projects_list:
            df_admin = pd.DataFrame(projects_list)[["project_code", "project_name", "project_password"]]
            st.write("Lista completa progetti e password attive:")
            st.table(df_admin)
            
            st.divider()
            st.subheader("Modifica o Elimina")
            proj_sel = st.selectbox("Seleziona Progetto:", {f"{p['project_code']} - {p['project_name']}": p for p in projects_list}.keys())
            target = {f"{p['project_code']} - {p['project_name']}": p for p in projects_list}[proj_sel]
            
            new_pw = st.text_input("Nuova Password Collaboratori", value=target.get('project_password'))
            if st.button("Aggiorna Password Progetto"):
                supabase.table("projects").update({"project_password": new_pw}).eq("id", target['id']).execute()
                st.success("Password aggiornata!")
                st.rerun()
