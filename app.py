import streamlit as st
import pandas as pd
from supabase import create_client, Client
import io

# --- SETUP SUPABASE ---
try:
    url = st.secrets["SUPABASE_URL"]
    key = st.secrets["SUPABASE_KEY"]
except:
    st.error("Configurazione mancante nei Secrets! Carica SUPABASE_URL e SUPABASE_KEY.")
    st.stop()

supabase: Client = create_client(url, key)

st.set_page_config(page_title="BIM Data Manager", layout="wide", page_icon="🏗️")

# --- RECUPERO PROGETTI ---
try:
    projects_resp = supabase.table("projects").select("id, project_name, project_code").execute()
    projects_list = projects_resp.data
except Exception as e:
    st.error(f"Errore di connessione al database: {e}")
    st.stop()

# --- BARRA DI NAVIGAZIONE ---
st.sidebar.title("🧭 Menu")
menu = st.sidebar.radio("Vai a:", ["Locali", "Mappatura Parametri", "Nuovo Progetto"])

# --- LOGICA PER LOCALI E MAPPATURA ---
if menu in ["Locali", "Mappatura Parametri"]:
    if not projects_list:
        st.sidebar.warning("Crea prima un progetto.")
        project_id = None
    else:
        st.sidebar.divider()
        project_options = {f"{p['project_code']} - {p['project_name']}": p for p in projects_list}
        selected_label = st.sidebar.selectbox("Progetto attivo:", list(project_options.keys()))
        selected_project = project_options[selected_label]
        project_id = selected_project['id']

    # --- HEADER AREA PRINCIPALE (A DESTRA) ---
    if project_id:
        # Creiamo due colonne: una per il titolo, una per il tasto gestione
        col_titolo, col_gestione = st.columns([3, 1])
        
        with col_titolo:
            st.title(f"{'📍' if menu == 'Locali' else '🔗'} {menu}")
            st.caption(f"Commessa corrente: **{selected_label}**")
        
        with col_gestione:
            st.write("") # Spazio estetico
            with st.expander("⚙️ Gestisci Progetto", expanded=False):
                st.subheader("Modifica Progetto")
                edit_code = st.text_input("Codice", value=selected_project['project_code'], key="edit_code")
                edit_name = st.text_input("Nome", value=selected_project['project_name'], key="edit_name")
                
                c1, c2 = st.columns(2)
                if c1.button("💾 Salva"):
                    supabase.table("projects").update({"project_code": edit_code, "project_name": edit_name}).eq("id", project_id).execute()
                    st.toast("Dati aggiornati!")
                    st.rerun()
                
                if c2.button("🔥 Elimina"):
                    st.session_state['show_delete_confirm'] = True
                
                # Sottosezione di conferma eliminazione se cliccato
                if st.session_state.get('show_delete_confirm'):
                    st.error("Conferma eliminazione scrivendo 'ELIMINA'")
                    conf = st.text_input("Conferma:", key="del_conf")
                    if st.button("Conferma Definitiva"):
                        if conf == "ELIMINA":
                            supabase.table("projects").delete().eq("id", project_id).execute()
                            st.rerun()

        st.divider()

    # --- 2. PAGINA: MAPPATURA PARAMETRI ---
    if menu == "Mappatura Parametri" and project_id:
        # ... [Resto del codice per Mappatura Parametri (Importazione, Form, Lista)]
        # (Codice identico al precedente per la gestione dati)
        with st.expander("📥 Importazione Massiva (Excel/CSV)"):
            # (Logica Excel...)
            pass
        st.subheader("📋 Configurazione Attiva")
        maps_resp = supabase.table("parameter_mappings").select("*").eq("project_id", project_id).execute()
        if maps_resp.data:
            st.dataframe(pd.DataFrame(maps_resp.data), use_container_width=True)

    # --- 3. PAGINA: LOCALI ---
    elif menu == "Locali" and project_id:
        # ... [Resto del codice per Locali]
        rooms_resp = supabase.table("rooms").select("*").eq("project_id", project_id).execute()
        st.dataframe(rooms_resp.data, use_container_width=True)

# --- 1. PAGINA: NUOVO PROGETTO ---
elif menu == "Nuovo Progetto":
    st.title("➕ Crea Nuovo Progetto")
    with st.form("form_crea_progetto"):
        new_code = st.text_input("Codice Progetto")
        new_name = st.text_input("Nome Progetto")
        if st.form_submit_button("Crea Progetto"):
            supabase.table("projects").insert({"project_code": new_code, "project_name": new_name}).execute()
            st.rerun()
