import streamlit as st
import pandas as pd
from supabase import create_client, Client
import io

# --- SETUP SUPABASE E ADMIN PWD ---
try:
    url = st.secrets["SUPABASE_URL"]
    key = st.secrets["SUPABASE_KEY"]
    admin_pwd = st.secrets["ADMIN_PASSWORD"] # La tua password master per Gestione Progetti
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
    st.error(f"Errore di connessione al database: {e}")
    st.stop()

# --- BARRA DI NAVIGAZIONE ---
st.sidebar.title("🏗️ BIM Data Manager")
menu = st.sidebar.radio("Vai a:", ["Locali", "Mappatura Parametri", "Gestione Progetti"])

# --- LOGICA DI ACCESSO PROGETTI (PER COLLABORATORI) ---
if menu in ["Locali", "Mappatura Parametri"]:
    if not projects_list:
        st.sidebar.warning("Nessun progetto disponibile. Contatta l'amministratore.")
        st.stop()

    st.sidebar.divider()
    project_options = {f"{p['project_code']} - {p['project_name']}": p for p in projects_list}
    selected_label = st.sidebar.selectbox("Seleziona Progetto:", list(project_options.keys()))
    project_data = project_options[selected_label]
    project_id = project_data['id']
    
    # Chiave di sessione specifica per questo progetto
    auth_key = f"auth_{project_id}"

    # GATE DI ACCESSO PROGETTO
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
                            st.error("Password errata. Riprova.")
        st.stop()

    # --- CONTENUTO PAGINE (ACCESSO CONSENTITO) ---
    st.title(f"{'📍' if menu == 'Locali' else '🔗'} {menu}")
    st.caption(f"Progetto Attivo: **{selected_label}**")
    
    if st.sidebar.button("🔒 Esci dal Progetto"):
        st.session_state[auth_key] = False
        st.rerun()

    # --- 1. PAGINA LOCALI ---
    if menu == "Locali":
        # Recupero mappature per colonne JSONB
        maps_resp = supabase.table("parameter_mappings").select("db_column_name").eq("project_id", project_id).execute()
        mapped_params = [m['db_column_name'] for m in maps_resp.data]

        with st.expander("📥 Import / Export / Reset Locali"):
            c1, c2, c3 = st.columns(3)
            with c1:
                st.write("**Esporta**")
                rooms_raw = supabase.table("rooms").select("*").eq("project_id", project_id).order("room_number").execute()
                export_data = []
                for r in rooms_raw.data:
                    row = {"room_number": r["room_number"], "room_name_planned": r["room_name_planned"]}
                    p_json = r.get("parameters") or {}
                    for p in mapped_params: row[p] = p_json.get(p, "")
                    export_data.append(row)
                df_export = pd.DataFrame(export_data) if export_data else pd.DataFrame(columns=["room_number", "room_name_planned"] + mapped_params)
                buf = io.BytesIO()
                with pd.ExcelWriter(buf, engine='xlsxwriter') as writer:
                    df_export.to_excel(writer, index=False)
                st.download_button("⬇️ Scarica Excel", data=buf.getvalue(), file_name=f"locali_{project_data['project_code']}.xlsx")
            
            with c2:
                st.write("**Importa (Upsert)**")
                up_rooms = st.file_uploader("Carica file Locali", type=["xlsx", "csv"], key="up_loc")
                if up_rooms and st.button("🚀 Sincronizza"):
                    df_up = pd.read_excel(up_rooms) if up_rooms.name.endswith('.xlsx') else pd.read_csv(up_rooms)
                    for _, row in df_up.iterrows():
                        r_num = str(row.get("room_number", "")).strip()
                        if r_num:
                            p_save = {p: str(row[p]) for p in mapped_params if p in row and pd.notna(row[p])}
                            exist = supabase.table("rooms").select("id").eq("project_id", project_id).eq("room_number", r_num).execute()
                            payload = {"project_id": project_id, "room_number": r_num, "room_name_planned": str(row.get("room_name_planned", "")), "parameters": p_save}
                            if exist.data: supabase.table("rooms").update(payload).eq("id", exist.data[0]["id"]).execute()
                            else: supabase.table("rooms").insert(payload).execute()
                    st.success("Dati sincronizzati!")
                    st.rerun()
            
            with c3:
                st.write("**Zona Pericolo**")
                if st.button("🗑️ SVUOTA TUTTI I LOCALI"):
                    supabase.table("rooms").delete().eq("project_id", project_id).execute()
                    st.rerun()

        st.divider()

        # Visualizzazione Editor Locali
        rooms_resp = supabase.table("rooms").select("*").eq("project_id", project_id).order("room_number").execute()
        if rooms_resp.data:
            flat_data = []
            for r in rooms_resp.data:
                row = {"id": r["id"], "room_number": r["room_number"], "room_name_planned": r["room_name_planned"]}
                p_json = r.get("parameters") or {}
                for p in mapped_params: row[p] = p_json.get(p, "")
                flat_data.append(row)

            df_rooms = pd.DataFrame(flat_data)
            df_rooms["Elimina"] = False
            
            st.subheader("📝 Editor Dati Locali")
            edited_df = st.data_editor(
                df_rooms,
                column_config={
                    "id": None, 
                    "room_number": st.column_config.TextColumn("Numero", disabled=True),
                    "Elimina": st.column_config.CheckboxColumn("Seleziona")
                },
                use_container_width=True, hide_index=True, key="editor_locali"
            )

            col_b1, col_b2 = st.columns(2)
            if col_b1.button("💾 SALVA MODIFICHE DATI", use_container_width=True, type="primary"):
                for _, row in edited_df.iterrows():
                    up_p = {p: row[p] for p in mapped_params if p in row}
                    supabase.table("rooms").update({
                        "room_name_planned": row["room_name_planned"], 
                        "parameters": up_p
                    }).eq("id", row["id"]).execute()
                st.success("Modifiche salvate con successo!")
                st.rerun()
            
            if col_b2.button("🗑️ ELIMINA RIGHE SELEZIONATE", use_container_width=True):
                to_del = edited_df[edited_df["Elimina"] == True]
                for _, r in to_del.iterrows():
                    supabase.table("rooms").delete().eq("id", r["id"]).execute()
                st.rerun()
        else:
            st.info("Nessun locale trovato. Carica un file Excel o aggiungine uno dalla sidebar.")

        with st.sidebar.expander("➕ Aggiungi Singolo Locale"):
            with st.form("new_room"):
                n_num = st.text_input("Numero")
                n_nam = st.text_input("Nome")
                if st.form_submit_button("Aggiungi"):
                    if n_num:
                        supabase.table("rooms").insert({"room_number": n_num, "room_name_planned": n_nam, "project_id": project_id, "parameters": {}}).execute()
                        st.rerun()

    # --- 2. PAGINA MAPPATURA ---
    elif menu == "Mappatura Parametri":
        with st.expander("📥 Import / Export Mappature"):
            c_m1, c_m2 = st.columns(2)
            with c_m1:
                st.write("**Esporta / Template**")
                res_m = supabase.table("parameter_mappings").select("*").eq("project_id", project_id).execute()
                df_m_exp = pd.DataFrame(res_m.data)[["db_column_name", "revit_parameter_name"]] if res_m.data else pd.DataFrame(columns=["Database", "Revit"])
                df_m_exp.columns = ["Database", "Revit"]
                buf_m = io.BytesIO()
                with pd.ExcelWriter(buf_m, engine='xlsxwriter') as writer:
                    df_m_exp.to_excel(writer, index=False)
                st.download_button("⬇️ Scarica Template", data=buf_m.getvalue(), file_name="mappe.xlsx")
            
            with c_m2:
                st.write("**Importa Mappe**")
                up_m = st.file_uploader("Carica file Mappe", type=["xlsx"])
                if up_m and st.button("🚀 Carica Mappature"):
                    df_m_up = pd.read_excel(up_m)
                    batch = [{"project_id": project_id, "db_column_name": str(r['Database']).strip(), "revit_parameter_name": str(r['Revit']).strip()} for _, r in df_m_up.dropna().iterrows()]
                    supabase.table("parameter_mappings").insert(batch).execute()
                    st.rerun()

        st.subheader("➕ Aggiungi Singola Mappatura")
        with st.form("single_map"):
            c1, c2 = st.columns(2)
            db_c = c1.text_input("Chiave Database (es. Fire_Rating)")
            rev_p = c2.text_input("Parametro Revit (es. Resistenza al Fuoco)")
            if st.form_submit_button("Salva"):
                if db_c and rev_p:
                    supabase.table("parameter_mappings").insert({"project_id": project_id, "db_column_name": db_c, "revit_parameter_name": rev_p}).execute()
                    st.rerun()

        res_map = supabase.table("parameter_mappings").select("*").eq("project_id", project_id).execute()
        if res_map.data:
            st.subheader("📋 Mappature Attive")
            df_m_view = pd.DataFrame(res_map.data)
            df_m_view["Elimina"] = False
            ed_map = st.data_editor(df_m_view[["id", "db_column_name", "revit_parameter_name", "Elimina"]], column_config={"id": None}, hide_index=True, use_container_width=True)
            if st.button("Conferma Modifiche/Eliminazioni Mappe"):
                for _, r in ed_map[ed_map["Elimina"]].iterrows():
                    supabase.table("parameter_mappings").delete().eq("id", r["id"]).execute()
                st.rerun()

# --- 3. PAGINA AREA ADMIN (GESTIONE PROGETTI) ---
elif menu == "Gestione Progetti":
    st.title("🛡️ Area Amministratore")
    
    # PROTEZIONE CON PASSWORD MASTER
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

    # CONTENUTO AREA ADMIN
    st.success("Accesso Admin Verificato")
    if st.sidebar.button("🔒 Esci da Area Admin"):
        st.session_state["admin_auth"] = False
        st.rerun()

    t1, t2 = st.tabs(["➕ Crea Nuovo Progetto", "📝 Gestisci/Vedi Password"])
    
    with t1:
        with st.form("new_prj_admin"):
            cp = st.text_input("Codice Progetto")
            np = st.text_input("Nome Progetto")
            pw = st.text_input("Password Collaboratori", placeholder="Password da dare al team")
            if st.form_submit_button("Crea Progetto"):
                if cp and np and pw:
                    supabase.table("projects").insert({"project_code": cp, "project_name": np, "project_password": pw}).execute()
                    st.success(f"Progetto {cp} creato correttamente!")
                    st.rerun()
                else:
                    st.error("Compila tutti i campi.")

    with t2:
        if projects_list:
            df_admin = pd.DataFrame(projects_list)[["id", "project_code", "project_name", "project_password"]]
            st.write("Lista completa progetti e password correnti:")
            st.dataframe(df_admin, use_container_width=True, hide_index=True)
            
            st.divider()
            st.subheader("Modifica o Elimina Progetto")
            proj_sel = st.selectbox("Seleziona Progetto:", {f"{p['project_code']} - {p['project_name']}": p for p in projects_list}.keys())
            target = {f"{p['project_code']} - {p['project_name']}": p for p in projects_list}[proj_sel]
            
            new_c = st.text_input("Codice", value=target['project_code'])
            new_n = st.text_input("Nome", value=target['project_name'])
            new_pw = st.text_input("Password Collaboratori", value=target.get('project_password', ""))
            
            c_s, c_d = st.columns(2)
            if c_s.button("💾 Salva Modifiche Progetto", use_container_width=True):
                supabase.table("projects").update({"project_code": new_c, "project_name": new_n, "project_password": new_pw}).eq("id", target['id']).execute()
                st.success("Progetto aggiornato!")
                st.rerun()
            
            if c_d.button("🔥 ELIMINA PROGETTO DEFINITIVAMENTE", use_container_width=True):
                # Nota: L'eliminazione a cascata dovrebbe essere gestita nel DB Supabase (Foreign Keys)
                supabase.table("projects").delete().eq("id", target['id']).execute()
                st.rerun()
        else:
            st.info("Nessun progetto esistente.")
