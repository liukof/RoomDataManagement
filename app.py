import streamlit as st
import pandas as pd
from supabase import create_client, Client
import io

# --- SETUP SUPABASE ---
try:
    url = st.secrets["SUPABASE_URL"]
    key = st.secrets["SUPABASE_KEY"]
except:
    st.error("Configurazione mancante nei Secrets!")
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

# --- LOGICA DI ACCESSO E PROTEZIONE ---
if menu in ["Locali", "Mappatura Parametri"]:
    if not projects_list:
        st.sidebar.warning("Crea prima un progetto.")
        st.stop()

    st.sidebar.divider()
    project_options = {f"{p['project_code']} - {p['project_name']}": p for p in projects_list}
    selected_label = st.sidebar.selectbox("Seleziona Progetto:", list(project_options.keys()))
    project_data = project_options[selected_label]
    project_id = project_data['id']
    
    # Chiave univoca per gestire la sessione di questo specifico progetto
    auth_key = f"auth_{project_id}"

    # SCHERMATA DI BLOCCO (Se non autenticato)
    if auth_key not in st.session_state or not st.session_state[auth_key]:
        # Pulizia layout per il Login
        st.title("🔒 Accesso Progetto Protetto")
        st.info(f"Il progetto **{selected_label}** richiede una chiave di accesso.")
        
        # Creazione di un form centrale
        with st.container():
            col_a, col_b, col_c = st.columns([1, 2, 1])
            with col_b:
                with st.form("login_gate"):
                    pwd_input = st.text_input("Password Progetto", type="password")
                    submit_login = st.form_submit_button("Sblocca Progetto", use_container_width=True)
                    
                    if submit_login:
                        correct_pwd = project_data.get('project_password', "")
                        if pwd_input == correct_pwd:
                            st.session_state[auth_key] = True
                            st.rerun()
                        else:
                            st.error("Password errata. Riprova o contatta l'amministratore.")
        st.stop() # FERMA IL RESTO DELL'APP QUI

    # --- SE AUTENTICATO, MOSTRA IL CONTENUTO ---
    st.title(f"{'📍' if menu == 'Locali' else '🔗'} {menu}")
    st.caption(f"Commessa: **{selected_label}**")
    if st.sidebar.button("🔒 Esci dal Progetto"):
        st.session_state[auth_key] = False
        st.rerun()

    # --- 1. PAGINA: LOCALI ---
    if menu == "Locali":
        maps_resp = supabase.table("parameter_mappings").select("db_column_name").eq("project_id", project_id).execute()
        mapped_params = [m['db_column_name'] for m in maps_resp.data]

        with st.expander("📥 Import / Export / Reset Locali"):
            c1, c2, c3 = st.columns(3)
            with c1:
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
                st.download_button("⬇️ Scarica Excel", data=buf.getvalue(), file_name=f"locali_{selected_label}.xlsx")
            with c2:
                up_rooms = st.file_uploader("Importa Excel", type=["xlsx"])
                if up_rooms and st.button("🚀 Sincronizza"):
                    df_up = pd.read_excel(up_rooms)
                    for _, row in df_up.iterrows():
                        r_num = str(row.get("room_number", "")).strip()
                        if r_num:
                            p_save = {p: str(row[p]) for p in mapped_params if p in row and pd.notna(row[p])}
                            exist = supabase.table("rooms").select("id").eq("project_id", project_id).eq("room_number", r_num).execute()
                            payload = {"project_id": project_id, "room_number": r_num, "room_name_planned": str(row.get("room_name_planned", "")), "parameters": p_save}
                            if exist.data: supabase.table("rooms").update(payload).eq("id", exist.data[0]["id"]).execute()
                            else: supabase.table("rooms").insert(payload).execute()
                    st.success("Sincronizzato!")
                    st.rerun()
            with c3:
                if st.button("🗑️ RESET TUTTO"):
                    supabase.table("rooms").delete().eq("project_id", project_id).execute()
                    st.rerun()

        st.divider()
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
            edited_df = st.data_editor(df_rooms, column_config={"id": None, "room_number": st.column_config.TextColumn("Numero", disabled=True), "Elimina": st.column_config.CheckboxColumn("Seleziona")}, use_container_width=True, hide_index=True)
            
            cb1, cb2 = st.columns(2)
            if cb1.button("💾 SALVA MODIFICHE", use_container_width=True, type="primary"):
                for _, row in edited_df.iterrows():
                    up_p = {p: row[p] for p in mapped_params if p in row}
                    supabase.table("rooms").update({"room_name_planned": row["room_name_planned"], "parameters": up_p}).eq("id", row["id"]).execute()
                st.rerun()
            if cb2.button("🗑️ ELIMINA SELEZIONATI", use_container_width=True):
                for _, r in edited_df[edited_df["Elimina"]].iterrows(): supabase.table("rooms").delete().eq("id", r["id"]).execute()
                st.rerun()

    # --- 2. PAGINA: MAPPATURA PARAMETRI ---
    elif menu == "Mappatura Parametri":
        with st.expander("📤 Import / Export Mappature"):
            res_m = supabase.table("parameter_mappings").select("*").eq("project_id", project_id).execute()
            df_m_exp = pd.DataFrame(res_m.data)[["db_column_name", "revit_parameter_name"]] if res_m.data else pd.DataFrame(columns=["Database", "Revit"])
            buf_m = io.BytesIO()
            with pd.ExcelWriter(buf_m, engine='xlsxwriter') as writer:
                df_m_exp.to_excel(writer, index=False)
            st.download_button("⬇️ Scarica Template", data=buf_m.getvalue(), file_name="mappe.xlsx")
            up_m = st.file_uploader("Carica Mappe", type=["xlsx"])
            if up_m and st.button("🚀 Carica"):
                df_m_up = pd.read_excel(up_m)
                batch = [{"project_id": project_id, "db_column_name": str(r['Database']).strip(), "revit_parameter_name": str(r['Revit']).strip()} for _, r in df_m_up.dropna().iterrows()]
                supabase.table("parameter_mappings").insert(batch).execute()
                st.rerun()

        st.subheader("➕ Aggiungi Mappatura")
        with st.form("single_map"):
            c1, c2 = st.columns(2)
            db_c = c1.text_input("Chiave Database")
            rev_p = c2.text_input("Parametro Revit")
            if st.form_submit_button("Salva"):
                if db_c and rev_p:
                    supabase.table("parameter_mappings").insert({"project_id": project_id, "db_column_name": db_c, "revit_parameter_name": rev_p}).execute()
                    st.rerun()
        
        res_map = supabase.table("parameter_mappings").select("*").eq("project_id", project_id).execute()
        if res_map.data:
            df_m_view = pd.DataFrame(res_map.data)
            df_m_view["Elimina"] = False
            ed_map = st.data_editor(df_m_view[["id", "db_column_name", "revit_parameter_name", "Elimina"]], column_config={"id": None}, hide_index=True)
            if st.button("Elimina Mappe Selezionate"):
                for _, r in ed_map[ed_map["Elimina"]].iterrows(): supabase.table("parameter_mappings").delete().eq("id", r["id"]).execute()
                st.rerun()

# --- 3. PAGINA: GESTIONE PROGETTI ---
elif menu == "Gestione Progetti":
    st.title("⚙️ Gestione Progetti")
    st.info("Qui imposti i codici e le password per i tuoi collaboratori.")
    t1, t2 = st.tabs(["➕ Nuovo Progetto", "📝 Modifica / Elimina"])
    
    with t1:
        with st.form("new_prj"):
            cp = st.text_input("Codice Progetto")
            np = st.text_input("Nome Progetto")
            pw = st.text_input("Imposta Password Progetto", placeholder="Scrivila qui...")
            if st.form_submit_button("Crea Progetto"):
                if cp and np and pw:
                    supabase.table("projects").insert({"project_code": cp, "project_name": np, "project_password": pw}).execute()
                    st.success(f"Progetto {cp} creato!")
                    st.rerun()

    with t2:
        if projects_list:
            proj_sel = st.selectbox("Seleziona Progetto:", {f"{p['project_code']} - {p['project_name']}": p for p in projects_list}.keys())
            target = {f"{p['project_code']} - {p['project_name']}": p for p in projects_list}[proj_sel]
            
            new_c = st.text_input("Modifica Codice", value=target['project_code'])
            new_n = st.text_input("Modifica Nome", value=target['project_name'])
            new_p = st.text_input("Modifica Password", value=target.get('project_password', ""))
            
            c_s, c_d = st.columns(2)
            if c_s.button("💾 Salva Modifiche"):
                supabase.table("projects").update({"project_code": new_c, "project_name": new_n, "project_password": new_p}).eq("id", target['id']).execute()
                st.success("Aggiornato!")
                st.rerun()
            if c_d.button("🔥 ELIMINA"):
                supabase.table("projects").delete().eq("id", target['id']).execute()
                st.rerun()
