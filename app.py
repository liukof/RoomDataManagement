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
menu = st.sidebar.radio("Vai a:", ["Locali", "Mappatura Parametri", "Gestione Progetti"])

# --- LOGICA COMUNE PER PROGETTI ---
if menu in ["Locali", "Mappatura Parametri"]:
    if not projects_list:
        st.sidebar.warning("Crea prima un progetto in 'Gestione Progetti'.")
        st.stop()

    st.sidebar.divider()
    project_options = {f"{p['project_code']} - {p['project_name']}": p for p in projects_list}
    selected_label = st.sidebar.selectbox("Progetto attivo:", list(project_options.keys()))
    selected_project = project_options[selected_label]
    project_id = selected_project['id']

    st.title(f"{'📍' if menu == 'Locali' else '🔗'} {menu}")
    st.caption(f"Commessa corrente: **{selected_label}**")
    st.divider()

    # --- 1. PAGINA: LOCALI (EDITOR DINAMICO) ---
    if menu == "Locali":
        # Scarichiamo i locali del progetto
        rooms_resp = supabase.table("rooms").select("*").eq("project_id", project_id).order("room_number").execute()
        
        if rooms_resp.data:
            df_rooms = pd.DataFrame(rooms_resp.data)
            
            # IDENTIFICAZIONE DINAMICA DELLE COLONNE
            # Escludiamo le colonne tecniche che l'utente non deve toccare
            cols_to_exclude = ["id", "project_id", "created_at", "revit_guid"]
            cols_to_edit = [col for col in df_rooms.columns if col not in cols_to_exclude]
            
            st.subheader("📝 Editor Dati Dinamico")
            st.info(f"Puoi modificare {len(cols_to_edit)} campi per ogni locale. Qualsiasi colonna aggiunta su Supabase apparirà qui automaticamente.")
            
            # Ordiniamo le colonne: Numero e Nome per primi
            main_cols = ["room_number", "room_name_planned"]
            other_cols = [c for c in cols_to_edit if c not in main_cols]
            display_order = main_cols + other_cols

            # EDITOR INTERATTIVO
            edited_df = st.data_editor(
                df_rooms,
                column_order=display_order,
                column_config={
                    "room_number": st.column_config.TextColumn("Numero Locale", disabled=True),
                    "room_name_planned": st.column_config.TextColumn("Nome Programmato"),
                },
                use_container_width=True,
                hide_index=True,
                key="dynamic_rooms_editor"
            )

            if st.button("💾 Salva Modifiche"):
                try:
                    success_count = 0
                    for _, row in edited_df.iterrows():
                        # Creiamo il dizionario dei dati da inviare basato sulle colonne attuali del DB
                        update_payload = {col: row[col] for col in cols_to_edit}
                        supabase.table("rooms").update(update_payload).eq("id", row["id"]).execute()
                        success_count += 1
                    
                    st.success(f"Aggiornati correttamente {success_count} locali!")
                    st.rerun()
                except Exception as e:
                    st.error(f"Errore durante il salvataggio: {e}")
        else:
            st.info("Nessun locale presente per questo progetto.")

        # Inserimento rapido via Sidebar
        with st.sidebar.expander("➕ Aggiungi Singolo Locale"):
            with st.form(key="form_fast_room", clear_on_submit=True):
                num = st.text_input("Numero Locale")
                nam = st.text_input("Nome Programmato")
                if st.form_submit_button("Salva"):
                    if num and nam:
                        supabase.table("rooms").insert({
                            "room_number": num,
                            "room_name_planned": nam,
                            "project_id": project_id
                        }).execute()
                        st.rerun()

    # --- 2. PAGINA: MAPPATURA PARAMETRI ---
    elif menu == "Mappatura Parametri":
        with st.expander("📥 Importazione Massiva Mappature (Excel/CSV)"):
            st.write("Usa questo strumento per caricare le corrispondenze tra colonne DB e parametri Revit.")
            
            # Generazione Template Excel
            template_df = pd.DataFrame(columns=["Database", "Revit"])
            buffer = io.BytesIO()
            with pd.ExcelWriter(buffer, engine='xlsxwriter') as writer:
                template_df.to_excel(writer, index=False, sheet_name='Sheet1')
            
            st.download_button(
                label="⬇️ Scarica Template Excel", 
                data=buffer.getvalue(), 
                file_name="template_mappatura.xlsx",
                mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
            )
            
            uploaded_file = st.file_uploader("Carica file compilato", type=["xlsx", "csv"])
            if uploaded_file:
                try:
                    df_import = pd.read_excel(uploaded_file) if uploaded_file.name.endswith('.xlsx') else pd.read_csv(uploaded_file)
                    if st.button("🚀 Conferma Importazione Massiva"):
                        batch = [
                            {
                                "project_id": project_id, 
                                "db_column_name": str(row['Database']).strip(), 
                                "revit_parameter_name": str(row['Revit']).strip()
                            } 
                            for _, row in df_import.dropna().iterrows()
                        ]
                        if batch:
                            supabase.table("parameter_mappings").insert(batch).execute()
                            st.success(f"Importate {len(batch)} mappature!")
                            st.rerun()
                except Exception as e:
                    st.error(f"Errore: {e}")

        st.subheader("➕ Aggiungi Singola Mappatura")
        with st.form("single_map"):
            c1, c2 = st.columns(2)
            db_c = c1.text_input("Nome Colonna Database (es. department)")
            rev_p = c2.text_input("Parametro Revit (es. Reparto)")
            if st.form_submit_button("Salva Associazione"):
                if db_c and rev_p:
                    supabase.table("parameter_mappings").insert({
                        "project_id": project_id, 
                        "db_column_name": db_c, 
                        "revit_parameter_name": rev_p
                    }).execute()
                    st.rerun()

        st.subheader("📋 Mappature Attive")
        maps_resp = supabase.table("parameter_mappings").select("*").eq("project_id", project_id).execute()
        if maps_resp.data:
            df_active_maps = pd.DataFrame(maps_resp.data)
            st.dataframe(df_active_maps[["db_column_name", "revit_parameter_name"]].rename(columns={
                "db_column_name": "Colonna DB", "revit_parameter_name": "Parametro Revit"
            }), use_container_width=True, hide_index=True)
            
            if st.button("🗑️ Reset Totale Mappature"):
                supabase.table("parameter_mappings").delete().eq("project_id", project_id).execute()
                st.rerun()
        else:
            st.info("Nessuna mappatura definita per questo progetto.")

# --- 3. PAGINA: GESTIONE PROGETTI ---
elif menu == "Gestione Progetti":
    st.title("⚙️ Gestione Progetti")
    t1, t2 = st.tabs(["➕ Nuovo Progetto", "📝 Modifica/Elimina"])
    
    with t1:
        with st.form("new_prj", clear_on_submit=True):
            c_p = st.text_input("Codice Progetto")
            n_p = st.text_input("Nome Progetto")
            if st.form_submit_button("Crea Progetto"):
                if c_p and n_p:
                    supabase.table("projects").insert({"project_code": c_p, "project_name": n_p}).execute()
                    st.success("Progetto creato con successo!")
                    st.rerun()

    with t2:
        if projects_list:
            proj_dict = {f"{p['project_code']} - {p['project_name']}": p for p in projects_list}
            selected_prj_key = st.selectbox("Seleziona Progetto da gestire:", list(proj_dict.keys()))
            target = proj_dict[selected_prj_key]
            
            edit_c = st.text_input("Codice", value=target['project_code'])
            edit_n = st.text_input("Nome", value=target['project_name'])
            
            col_save, col_del = st.columns(2)
            if col_save.button("💾 Salva Modifiche Nome/Codice"):
                supabase.table("projects").update({"project_code": edit_c, "project_name": edit_n}).eq("id", target['id']).execute()
                st.success("Dati aggiornati!")
                st.rerun()
            
            st.divider()
            st.warning("⚠️ L'eliminazione è irreversibile e cancellerà anche i locali e le mappe associate.")
            del_confirm = st.text_input("Per confermare l'eliminazione, scrivi ELIMINA")
            if col_del.button("🔥 Elimina Progetto"):
                if del_confirm == "ELIMINA":
                    supabase.table("projects").delete().eq("id", target['id']).execute()
                    st.rerun()
                else:
                    st.error("Scrivi ELIMINA per procedere.")
