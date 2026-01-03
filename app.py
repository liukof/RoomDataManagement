import streamlit as st
import pandas as pd
from supabase import create_client, Client
import io

# --- SETUP SUPABASE ---
try:
    url = st.secrets["SUPABASE_URL"]
    key = st.secrets["SUPABASE_KEY"]
except:
    st.error("Configurazione mancante nei Secrets (SUPABASE_URL, SUPABASE_KEY)!")
    st.stop()

supabase: Client = create_client(url, key)

st.set_page_config(page_title="BIM Data Manager PRO", layout="wide", page_icon="🏗️")

# --- LOGICA DI AUTENTICAZIONE (Google Email Based) ---
if "user_data" not in st.session_state:
    st.title("🏗️ BIM Data Manager - Login")
    st.write("Inserisci la tua email aziendale Google per accedere.")
    
    email_input = st.text_input("Email Google Workspace").lower().strip()
    if st.button("Accedi"):
        if email_input:
            # Verifica se l'utente è nella tabella user_permissions
            res = supabase.table("user_permissions").select("*").eq("email", email_input).execute()
            if res.data:
                st.session_state["user_data"] = res.data[0]
                st.success(f"Benvenuto {email_input}")
                st.rerun()
            else:
                st.error("Accesso negato. Questa email non è stata autorizzata dall'amministratore.")
        else:
            st.warning("Inserisci un'email valida.")
    st.stop()

# Dati utente loggato
current_user = st.session_state["user_data"]
is_admin = current_user.get("is_admin", False)
allowed_project_ids = current_user.get("allowed_projects", [])

# --- RECUPERO PROGETTI AUTORIZZATI ---
try:
    query = supabase.table("projects").select("*").order("project_code")
    if not is_admin:
        # Se non è admin, filtra solo per i progetti autorizzati nell'array
        query = query.in_("id", allowed_project_ids)
    
    projects_resp = query.execute()
    projects_list = projects_resp.data
except Exception as e:
    st.error(f"Errore nel recupero progetti: {e}")
    st.stop()

# --- SIDEBAR NAVIGAZIONE ---
st.sidebar.title(f"👤 {current_user['email']}")
if is_admin: st.sidebar.info("Profilo: AMMINISTRATORE")

menu_options = ["📍 Locali", "🔗 Mappatura Parametri"]
if is_admin: menu_options.append("⚙️ Gestione Sistema")

menu = st.sidebar.radio("Vai a:", menu_options)

if st.sidebar.button("Esci / Cambia Utente"):
    del st.session_state["user_data"]
    st.rerun()

# --- PAGINA: LOCALI ---
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
                st.download_button("⬇️ Scarica Excel", data=buf.getvalue(), file_name=f"locali_{selected_label}.xlsx")
            
            with c2:
                up_rooms = st.file_uploader("Carica file Locali", type=["xlsx"])
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
                    st.success("Sincronizzazione completata!")
                    st.rerun()
            
            with c3:
                if st.button("🗑️ SVUOTA TUTTI I LOCALI"):
                    supabase.table("rooms").delete().eq("project_id", project_id).execute()
                    st.rerun()

        st.divider()

        # Editor Dati
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
            
            b1, b2 = st.columns(2)
            if b1.button("💾 SALVA MODIFICHE", use_container_width=True, type="primary"):
                for _, row in edited_df.iterrows():
                    up_p = {p: row[p] for p in mapped_params if p in row}
                    supabase.table("rooms").update({"room_name_planned": row["room_name_planned"], "parameters": up_p}).eq("id", row["id"]).execute()
                st.rerun()
            if b2.button("🗑️ ELIMINA RIGHE SELEZIONATE", use_container_width=True):
                for _, r in edited_df[edited_df["Elimina"]].iterrows():
                    supabase.table("rooms").delete().eq("id", r["id"]).execute()
                st.rerun()

# --- PAGINA: MAPPATURA PARAMETRI ---
elif menu == "🔗 Mappatura Parametri":
    if not projects_list:
        st.warning("Nessun progetto disponibile.")
    else:
        project_options = {f"{p['project_code']} - {p['project_name']}": p for p in projects_list}
        selected_label = st.selectbox("Seleziona Progetto:", list(project_options.keys()))
        project_id = project_options[selected_label]['id']

        with st.form("add_map"):
            c1, c2 = st.columns(2)
            db_c = c1.text_input("Chiave Database")
            rev_p = c2.text_input("Parametro Revit")
            if st.form_submit_button("Aggiungi Mappatura"):
                if db_c and rev_p:
                    supabase.table("parameter_mappings").insert({"project_id": project_id, "db_column_name": db_c, "revit_parameter_name": rev_p}).execute()
                    st.rerun()

        res_map = supabase.table("parameter_mappings").select("*").eq("project_id", project_id).execute()
        if res_map.data:
            df_m = pd.DataFrame(res_map.data)
            df_m["Elimina"] = False
            ed_m = st.data_editor(df_m[["id", "db_column_name", "revit_parameter_name", "Elimina"]], column_config={"id": None}, use_container_width=True, hide_index=True)
            if st.button("Elimina Mappature Selezionate"):
                for _, r in ed_m[ed_m["Elimina"]].iterrows():
                    supabase.table("parameter_mappings").delete().eq("id", r["id"]).execute()
                st.rerun()

# --- PAGINA: GESTIONE SISTEMA (ADMIN ONLY) ---
elif menu == "⚙️ Gestione Sistema" and is_admin:
    st.title("🛡️ Amministrazione Sistema")
    t1, t2, t3 = st.tabs(["🏗️ Progetti", "👥 Utenti", "🔗 Assegna Accessi"])

    with t1:
        st.subheader("Crea o Modifica Progetti")
        with st.form("new_prj"):
            c1, c2 = st.columns(2)
            cp = c1.text_input("Codice Progetto")
            np = c2.text_input("Nome Progetto")
            if st.form_submit_button("Crea Progetto"):
                supabase.table("projects").insert({"project_code": cp, "project_name": np}).execute()
                st.rerun()

    with t2:
        st.subheader("Whitelist Email Utenti")
        with st.form("new_user"):
            nu_email = st.text_input("Email Google Workspace").lower().strip()
            nu_admin = st.checkbox("È Amministratore?")
            if st.form_submit_button("Autorizza Utente"):
                supabase.table("user_permissions").insert({"email": nu_email, "is_admin": nu_admin, "allowed_projects": []}).execute()
                st.rerun()
        
        all_u = supabase.table("user_permissions").select("*").execute().data
        if all_u:
            st.table(pd.DataFrame(all_u)[["email", "is_admin"]])

    with t3:
        st.subheader("Assegna Progetti a Utente")
        all_u = supabase.table("user_permissions").select("*").execute().data
        all_p = supabase.table("projects").select("*").execute().data
        
        if all_u and all_p:
            target_email = st.selectbox("Scegli Utente:", [u['email'] for u in all_u])
            target_user = next(u for u in all_u if u['email'] == target_email)
            
            p_map = {f"{p['project_code']} - {p['project_name']}": p['id'] for p in all_p}
            current_allowed = [f"{p['project_code']} - {p['project_name']}" for p in all_p if p['id'] in (target_user['allowed_projects'] or [])]
            
            new_selection = st.multiselect("Progetti autorizzati:", list(p_map.keys()), default=current_allowed)
            
            if st.button("Aggiorna Accessi"):
                new_ids = [p_map[name] for name in new_selection]
                supabase.table("user_permissions").update({"allowed_projects": new_ids}).eq("email", target_email).execute()
                st.success("Permessi aggiornati!")
                st.rerun()
