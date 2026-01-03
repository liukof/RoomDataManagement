import streamlit as st
import pandas as pd
from supabase import create_client, Client
import io

# --- 1. SETUP SUPABASE ---
try:
    url = st.secrets["SUPABASE_URL"]
    key = st.secrets["SUPABASE_KEY"]
except:
    st.error("Configurazione mancante nei Secrets! Assicurati di avere SUPABASE_URL e SUPABASE_KEY.")
    st.stop()

supabase: Client = create_client(url, key)

st.set_page_config(page_title="BIM Data Manager PRO", layout="wide", page_icon="🏗️")

# --- 2. LOGICA DI AUTENTICAZIONE (Whitelist Email) ---
if "user_data" not in st.session_state:
    st.title("🏗️ BIM Data Manager - Login")
    st.markdown("### Accesso con Email Aziendale")
    
    email_input = st.text_input("Indirizzo Email", placeholder="esempio@gmail.com").lower().strip()
    
    if st.button("Accedi", use_container_width=True, type="primary"):
        if email_input:
            res = supabase.table("user_permissions").select("*").eq("email", email_input).execute()
            
            if res.data and len(res.data) > 0:
                st.session_state["user_data"] = res.data[0]
                st.success(f"Benvenuto {email_input}! Caricamento...")
                st.rerun()
            else:
                st.error("🚫 Utente non registrato")
                st.info(f"L'email **{email_input}** non è presente nella whitelist. Contatta l'amministratore per richiedere l'accesso.")
        else:
            st.warning("⚠️ Inserisci un indirizzo email.")
    st.stop()

# Dati sessione
current_user = st.session_state["user_data"]
is_admin = current_user.get("is_admin", False)
allowed_project_ids = current_user.get("allowed_projects") or []

# --- 3. RECUPERO PROGETTI ---
try:
    query = supabase.table("projects").select("*").order("project_code")
    if not is_admin:
        # Se non admin, filtra solo per i progetti autorizzati (UUID validi)
        query = query.in_("id", allowed_project_ids if allowed_project_ids else ['00000000-0000-0000-0000-000000000000'])
    projects_list = query.execute().data
except Exception as e:
    st.error(f"Errore caricamento progetti: {e}")
    st.stop()

# --- 4. SIDEBAR ---
st.sidebar.title("🏗️ BIM Manager")
st.sidebar.caption(f"Utente: **{current_user['email']}**")
if is_admin: st.sidebar.info("Profilo: AMMINISTRATORE")

menu_opt = ["📍 Locali", "🔗 Mappatura Parametri"]
if is_admin: menu_opt.append("⚙️ Gestione Sistema")

menu = st.sidebar.radio("Vai a:", menu_opt)

if st.sidebar.button("🚪 Esci"):
    del st.session_state["user_data"]
    st.rerun()

# --- 5. PAGINA: LOCALI ---
if menu == "📍 Locali":
    if not projects_list:
        st.warning("Non hai progetti assegnati. Contatta l'amministratore.")
    else:
        project_options = {f"{p['project_code']} - {p['project_name']}": p for p in projects_list}
        selected_label = st.selectbox("Seleziona Progetto:", list(project_options.keys()))
        project_id = project_options[selected_label]['id']

        # Recupero mappature
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
                df_export = pd.DataFrame(export_data)
                buf = io.BytesIO()
                with pd.ExcelWriter(buf, engine='xlsxwriter') as writer:
                    df_export.to_excel(writer, index=False)
                st.download_button("⬇️ Scarica Excel", data=buf.getvalue(), file_name=f"locali_{project_id}.xlsx")
            
            with c2:
                st.write("**Importa (Upsert)**")
                up_rooms = st.file_uploader("Carica Excel Locali", type=["xlsx"])
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
                st.write("**Reset**")
                if st.button("🗑️ SVUOTA TUTTI I LOCALI"):
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
            edited_df = st.data_editor(df_rooms, column_config={"id": None, "room_number": st.column_config.TextColumn("Numero", disabled=True)}, use_container_width=True, hide_index=True)
            
            col_b1, col_b2 = st.columns(2)
            if col_b1.button("💾 SALVA MODIFICHE", use_container_width=True, type="primary"):
                for _, row in edited_df.iterrows():
                    up_p = {p: row[p] for p in mapped_params if p in row}
                    supabase.table("rooms").update({"room_name_planned": row["room_name_planned"], "parameters": up_p}).eq("id", row["id"]).execute()
                st.rerun()
            if col_b2.button("🗑️ ELIMINA SELEZIONATI", use_container_width=True):
                for _, r in edited_df[edited_df["Elimina"]].iterrows():
                    supabase.table("rooms").delete().eq("id", r["id"]).execute()
                st.rerun()

# --- 6. PAGINA: MAPPATURA PARAMETRI ---
elif menu == "🔗 Mappatura Parametri":
    project_options = {f"{p['project_code']} - {p['project_name']}": p for p in projects_list}
    selected_label = st.selectbox("Progetto:", list(project_options.keys()))
    project_id = project_options[selected_label]['id']

    with st.expander("📥 Import / Export Mappature"):
        cm1, cm2 = st.columns(2)
        with cm1:
            res_m = supabase.table("parameter_mappings").select("*").eq("project_id", project_id).execute()
            df_m_exp = pd.DataFrame(res_m.data)[["db_column_name", "revit_parameter_name"]] if res_m.data else pd.DataFrame(columns=["Database", "Revit"])
            df_m_exp.columns = ["Database", "Revit"]
            buf_m = io.BytesIO()
            with pd.ExcelWriter(buf_m, engine='xlsxwriter') as writer:
                df_m_exp.to_excel(writer, index=False)
            st.download_button("⬇️ Scarica Template", data=buf_m.getvalue(), file_name="mappe.xlsx")
        with cm2:
            up_m = st.file_uploader("Carica Excel Mappe", type=["xlsx"])
            if up_m and st.button("🚀 Carica"):
                df_m_up = pd.read_excel(up_m)
                batch = [{"project_id": project_id, "db_column_name": str(r['Database']).strip(), "revit_parameter_name": str(r['Revit']).strip()} for _, r in df_m_up.dropna().iterrows()]
                supabase.table("parameter_mappings").insert(batch).execute()
                st.rerun()

    with st.form("add_map"):
        c1, c2 = st.columns(2)
        if st.form_submit_button("➕ Aggiungi Singola Mappa"):
            if c1.text_input("Chiave DB") and c2.text_input("Parametro Revit"):
                supabase.table("parameter_mappings").insert({"project_id": project_id, "db_column_name": c1.text_input("Chiave DB"), "revit_parameter_name": c2.text_input("Parametro Revit")}).execute()
                st.rerun()

    res_map = supabase.table("parameter_mappings").select("*").eq("project_id", project_id).execute()
    if res_map.data:
        df_m = pd.DataFrame(res_map.data)
        df_m["Elimina"] = False
        ed_m = st.data_editor(df_m[["id", "db_column_name", "revit_parameter_name", "Elimina"]], column_config={"id": None}, use_container_width=True, hide_index=True)
        if st.button("Rimuovi Mappe Selezionate"):
            for _, r in ed_m[ed_m["Elimina"]].iterrows():
                supabase.table("parameter_mappings").delete().eq("id", r["id"]).execute()
            st.rerun()

# --- 7. GESTIONE SISTEMA (ADMIN ONLY) ---
elif menu == "⚙️ Gestione Sistema" and is_admin:
    st.title("🛡️ Amministrazione")
    t1, t2, t3 = st.tabs(["🏗️ Progetti", "👥 Utenti", "🔗 Accessi"])

    with t1:
        with st.form("new_p"):
            cp = st.text_input("Codice")
            np = st.text_input("Nome")
            if st.form_submit_button("Crea Progetto"):
                supabase.table("projects").insert({"project_code": cp, "project_name": np}).execute()
                st.rerun()
        
        st.subheader("Gestione Progetti")
        all_p_admin = supabase.table("projects").select("*").order("project_code").execute().data
        if all_p_admin:
            df_p_edit = pd.DataFrame(all_p_admin)[["id", "project_code", "project_name"]]
            df_p_edit["Elimina"] = False
            ed_p = st.data_editor(df_p_edit, column_config={"id": None}, use_container_width=True, hide_index=True)
            col_p1, col_p2 = st.columns(2)
            if col_p1.button("💾 SALVA NOMI"):
                for _, r in ed_p.iterrows():
                    supabase.table("projects").update({"project_code": r["project_code"], "project_name": r["project_name"]}).eq("id", r["id"]).execute()
                st.rerun()
            if col_p2.button("🔥 ELIMINA SELEZIONATI"):
                for _, r in ed_p[ed_p["Elimina"]].iterrows():
                    supabase.table("projects").delete().eq("id", r["id"]).execute()
                st.rerun()

    with t2:
        with st.form("new_u"):
            em = st.text_input("Email").lower().strip()
            ad = st.checkbox("Admin")
            if st.form_submit_button("Autorizza Utente"):
                supabase.table("user_permissions").insert({"email": em, "is_admin": ad, "allowed_projects": []}).execute()
                st.rerun()
        all_u = supabase.table("user_permissions").select("*").execute().data
        if all_u:
            st.table(pd.DataFrame(all_u)[["email", "is_admin"]])

    with t3:
        all_users = supabase.table("user_permissions").select("*").eq("is_admin", False).execute().data
        all_projects = supabase.table("projects").select("*").execute().data
        if all_users and all_projects:
            target = st.selectbox("Seleziona Utente:", [u['email'] for u in all_users])
            u_data = next(u for u in all_users if u['email'] == target)
            p_map = {f"{p['project_code']}": p['id'] for p in all_projects}
            
            # Fix UUID Array
            current_ids = u_data.get('allowed_projects') or []
            current_codes = [p['project_code'] for p in all_projects if p['id'] in current_ids]
            
            new_sel = st.multiselect("Assegna Progetti:", list(p_map.keys()), default=current_codes)
            if st.button("Aggiorna Accessi"):
                new_ids = [p_map[c] for c in new_sel]
                supabase.table("user_permissions").update({"allowed_projects": new_ids}).eq("email", target).execute()
                st.success("Accessi aggiornati!")
                st.rerun()
