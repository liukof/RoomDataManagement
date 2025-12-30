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

# --- LOGICA PER LOCALI E MAPPATURA ---
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

    # --- 1. PAGINA: LOCALI (CON EDITOR) ---
    if menu == "Locali":
        rooms_resp = supabase.table("rooms").select("*").eq("project_id", project_id).order("room_number").execute()
        
        if rooms_resp.data:
            df_rooms = pd.DataFrame(rooms_resp.data)
            
            # Identifichiamo le colonne dinamiche (escludendo quelle tecniche)
            cols_to_edit = [col for col in df_rooms.columns if col not in ["id", "project_id", "created_at"]]
            
            st.subheader("📝 Editor Dati")
            st.info("Modifica i valori nelle celle e premi 'Salva Modifiche' per aggiornare il database.")
            
            # EDITOR DATI INTERATTIVO
            edited_df = st.data_editor(
                df_rooms,
                column_order=["room_number", "room_name_planned"] + [c for c in cols_to_edit if c not in ["room_number", "room_name_planned"]],
                column_config={
                    "room_number": st.column_config.TextColumn("Numero Locale", disabled=True),
                    "room_name_planned": st.column_config.TextColumn("Nome Programmato"),
                },
                use_container_width=True,
                hide_index=True,
                key="rooms_data_editor"
            )

            if st.button("💾 Salva Modifiche"):
                try:
                    # Aggiornamento massivo riga per riga
                    for _, row in edited_df.iterrows():
                        # Creiamo un dizionario dei dati da aggiornare (escludendo l'ID)
                        update_data = {col: row[col] for col in cols_to_edit}
                        supabase.table("rooms").update(update_data).eq("id", row["id"]).execute()
                    
                    st.success("Database aggiornato correttamente!")
                    st.rerun()
                except Exception as e:
                    st.error(f"Errore durante il salvataggio: {e}")
        else:
            st.info("Nessun locale presente per questo progetto.")

        with st.sidebar.expander("➕ Inserimento Rapido Locale"):
            with st.form(key="form_fast_room", clear_on_submit=True):
                num = st.text_input("Numero Locale")
                nam = st.text_input("Nome Programmato")
                if st.form_submit_button("Aggiungi"):
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
            template_df = pd.DataFrame(columns=["Database", "Revit"])
            buffer = io.BytesIO()
            with pd.ExcelWriter(buffer, engine='xlsxwriter') as writer:
                template_df.to_excel(writer, index=False)
            
            st.download_button("⬇️ Scarica Template", data=buffer.getvalue(), file_name="template_mappatura.xlsx")
            
            uploaded_file = st.file_uploader("Carica file compilato", type=["xlsx", "csv"])
            if uploaded_file:
                df_import = pd.read_excel(uploaded_file) if uploaded_file.name.endswith('.xlsx') else pd.read_csv(uploaded_file)
                if st.button("🚀 Conferma Importazione"):
                    batch = [{"project_id": project_id, "db_column_name": str(row['Database']).strip(), "revit_parameter_name": str(row['Revit']).strip()} 
                             for _, row in df_import.dropna().iterrows()]
                    if batch:
                        supabase.table("parameter_mappings").insert(batch).execute()
                        st.rerun()

        st.subheader("➕ Aggiungi Singola Mappatura")
        with st.form("single_map"):
            c1, c2 = st.columns(2)
            db_c = c1.text_input("Colonna Database (es. room_name_planned)")
            rev_p = c2.text_input("Parametro Revit (es. Nome)")
            if st.form_submit_button("Salva"):
                supabase.table("parameter_mappings").insert({"project_id": project_id, "db_column_name": db_c, "revit_parameter_name": rev_p}).execute()
                st.rerun()

        st.subheader("📋 Mappature Attive")
        maps_resp = supabase.table("parameter_mappings").select("*").eq("project_id", project_id).execute()
        if maps_resp.data:
            st.dataframe(pd.DataFrame(maps_resp.data)[["db_column_name", "revit_parameter_name"]], use_container_width=True)
            if st.button("🗑️ Reset Mappature"):
                supabase.table("parameter_mappings").delete().eq("project_id", project_id).execute()
                st.rerun()

# --- 3. PAGINA: GESTIONE PROGETTI ---
elif menu == "Gestione Progetti":
    st.title("⚙️ Gestione Progetti")
    t1, t2 = st.tabs(["➕ Nuovo Progetto", "📝 Modifica/Elimina"])
    
    with t1:
        with st.form("new_prj"):
            c_p = st.text_input("Codice Progetto")
            n_p = st.text_input("Nome Progetto")
            if st.form_submit_button("Crea"):
                supabase.table("projects").insert({"project_code": c_p, "project_name": n_p}).execute()
                st.rerun()

    with t2:
        if projects_list:
            proj_to_edit = st.selectbox("Seleziona Progetto:", {f"{p['project_code']} - {p['project_name']}": p for p in projects_list}.keys())
            target = {f"{p['project_code']} - {p['project_name']}": p for p in projects_list}[proj_to_edit]
            
            new_c = st.text_input("Codice", value=target['project_code'])
            new_n = st.text_input("Nome", value=target['project_name'])
            
            col_s, col_e = st.columns(2)
            if col_s.button("💾 Salva Modifiche"):
                supabase.table("projects").update({"project_code": new_c, "project_name": new_n}).eq("id", target['id']).execute()
                st.rerun()
                
            st.divider()
            del_confirm = st.text_input("Scrivi 'ELIMINA' per confermare la cancellazione")
            if col_e.button("🔥 Elimina Progetto"):
                if del_confirm == "ELIMINA":
                    supabase.table("projects").delete().eq("id", target['id']).execute()
                    st.rerun()
