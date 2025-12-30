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
# Rinominiamo la voce come da tua proposta
menu = st.sidebar.radio("Vai a:", ["Locali", "Mappatura Parametri", "Gestione Progetti"])

# --- LOGICA PER LOCALI E MAPPATURA ---
if menu in ["Locali", "Mappatura Parametri"]:
    if not projects_list:
        st.sidebar.warning("Vai in 'Gestione Progetti' per creare una commessa.")
        st.stop()

    st.sidebar.divider()
    project_options = {f"{p['project_code']} - {p['project_name']}": p for p in projects_list}
    selected_label = st.sidebar.selectbox("Progetto attivo:", list(project_options.keys()))
    selected_project = project_options[selected_label]
    project_id = selected_project['id']

    st.title(f"{'📍' if menu == 'Locali' else '🔗'} {menu}")
    st.caption(f"Commessa corrente: **{selected_label}**")
    st.divider()

    # --- PAGINA: MAPPATURA PARAMETRI ---
    if menu == "Mappatura Parametri":
        with st.expander("📥 Importazione Massiva (Excel/CSV)"):
            st.write("Scarica il template, compilalo e caricalo per mappare i parametri Revit.")
            template_df = pd.DataFrame(columns=["Database", "Revit"])
            buffer = io.BytesIO()
            with pd.ExcelWriter(buffer, engine='xlsxwriter') as writer:
                template_df.to_excel(writer, index=False, sheet_name='Mappatura')
            
            st.download_button("⬇️ Scarica Template Excel", data=buffer.getvalue(), file_name="template_mappatura.xlsx")
            
            uploaded_file = st.file_uploader("Carica file compilato", type=["xlsx", "csv"])
            if uploaded_file:
                df_import = pd.read_excel(uploaded_file) if uploaded_file.name.endswith('.xlsx') else pd.read_csv(uploaded_file)
                st.dataframe(df_import.dropna(how='all'), height=150, hide_index=True)
                if st.button("🚀 Conferma Importazione"):
                    batch = [{"project_id": project_id, "db_column_name": str(row['Database']).strip(), "revit_parameter_name": str(row['Revit']).strip()} 
                             for _, row in df_import.dropna(subset=["Database", "Revit"]).iterrows()]
                    if batch:
                        supabase.table("parameter_mappings").insert(batch).execute()
                        st.success("Importazione completata!")
                        st.rerun()

        st.subheader("➕ Aggiungi Singola Associazione")
        with st.form(key="form_mapping_single", clear_on_submit=True):
            c1, c2 = st.columns(2)
            db_col = c1.text_input("Colonna Database")
            rev_param = c2.text_input("Parametro Revit")
            if st.form_submit_button("Salva"):
                if db_col and rev_param:
                    supabase.table("parameter_mappings").insert({"project_id": project_id, "db_column_name": db_col, "revit_parameter_name": rev_param}).execute()
                    st.rerun()

        st.subheader("📋 Configurazione Attiva")
        maps_resp = supabase.table("parameter_mappings").select("*").eq("project_id", project_id).execute()
        if maps_resp.data:
            df_active = pd.DataFrame(maps_resp.data)
            st.dataframe(df_active[["db_column_name", "revit_parameter_name"]].rename(columns={"db_column_name": "Database", "revit_parameter_name": "Revit"}), use_container_width=True, hide_index=True)
            if st.button("🗑️ Reset Mappature"):
                supabase.table("parameter_mappings").delete().eq("project_id", project_id).execute()
                st.rerun()

    # --- PAGINA: LOCALI ---
    elif menu == "Locali":
        rooms_resp = supabase.table("rooms").select("*").eq("project_id", project_id).execute()
        if rooms_resp.data:
            st.dataframe(rooms_resp.data, use_container_width=True)
        else:
            st.info("Nessun locale trovato.")
        
        with st.sidebar.expander("➕ Inserimento Rapido"):
            with st.form("fast_room", clear_on_submit=True):
                n_loc = st.text_input("Numero")
                nom_loc = st.text_input("Nome")
                if st.form_submit_button("Aggiungi"):
                    supabase.table("rooms").insert({"room_number": n_loc, "room_name_planned": nom_loc, "project_id": project_id}).execute()
                    st.rerun()

# --- 1. PAGINA: GESTIONE PROGETTI (CENTRALIZZATA) ---
elif menu == "Gestione Progetti":
    st.title("⚙️ Gestione Progetti")
    st.write("In questa sezione puoi creare nuovi progetti, rinominare quelli esistenti o eliminarli.")
    
    tab_nuovo, tab_modifica = st.tabs(["➕ Crea Nuovo", "📝 Modifica / Elimina Esistente"])
    
    with tab_nuovo:
        st.subheader("Registra una nuova commessa")
        with st.form("crea_progetto"):
            n_code = st.text_input("Codice Progetto (es. PRJ-01)")
            n_name = st.text_input("Nome Progetto (es. Ospedale Centrale)")
            if st.form_submit_button("Crea Progetto"):
                if n_code and n_name:
                    supabase.table("projects").insert({"project_code": n_code, "project_name": n_name}).execute()
                    st.success("Progetto creato!")
                    st.rerun()

    with tab_modifica:
        if not projects_list:
            st.info("Non ci sono progetti da modificare.")
        else:
            st.subheader("Seleziona il progetto da gestire")
            # Lista per selezione
            options_edit = {f"{p['project_code']} - {p['project_name']}": p for p in projects_list}
            target_label = st.selectbox("Progetto da modificare:", list(options_edit.keys()), key="select_edit")
            target_proj = options_edit[target_label]
            
            st.divider()
            
            col1, col2 = st.columns(2)
            
            with col1:
                st.markdown("### 📝 Rinomina")
                new_c = st.text_input("Nuovo Codice", value=target_proj['project_code'])
                new_n = st.text_input("Nuovo Nome", value=target_proj['project_name'])
                if st.button("💾 Salva Modifiche"):
                    supabase.table("projects").update({"project_code": new_c, "project_name": new_n}).eq("id", target_proj['id']).execute()
                    st.success("Dati aggiornati!")
                    st.rerun()
            
            with col2:
                st.markdown("### 🗑️ Eliminazione")
                st.warning("L'eliminazione è irreversibile e cancellerà tutti i locali associati.")
                conf_text = st.text_input("Scrivi 'ELIMINA' per confermare:", key="delete_confirm_page")
                if st.button("🔥 Elimina Progetto"):
                    if conf_text == "ELIMINA":
                        supabase.table("projects").delete().eq("id", target_proj['id']).execute()
                        st.success("Progetto eliminato.")
                        st.rerun()
                    else:
                        st.error("Testo di conferma non corretto.")
