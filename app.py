import streamlit as st
import pandas as pd
from supabase import create_client, Client
import io

# --- 1. SUPABASE SETUP ---
try:
    url = st.secrets["SUPABASE_URL"]
    key = st.secrets["SUPABASE_KEY"]
except:
    st.error("Configurazione mancante nei Secrets! (SUPABASE_URL, SUPABASE_KEY)")
    st.stop()

@st.cache_resource
def get_supabase_client():
    return create_client(url, key)

supabase: Client = get_supabase_client()

st.set_page_config(page_title="BIM Data Manager PRO", layout="wide", page_icon="🏗️")

# --- 2. AUTHENTICATION ---
if "user_data" not in st.session_state:
    st.session_state["user_data"] = None

if st.session_state["user_data"] is None:
    st.title("🏗️ BIM Data Manager - Login")
    with st.form("login_form"):
        email_input = st.text_input("Email", placeholder="nome@azienda.it").lower().strip()
        submit_login = st.form_submit_button("Accedi", use_container_width=True, type="primary")
    if submit_login:
        res = supabase.table("user_permissions").select("*").eq("email", email_input).execute()
        if res.data:
            st.session_state["user_data"] = res.data[0]
            st.rerun()
        else:
            st.error("Utente non autorizzato.")
    st.stop()

current_user = st.session_state["user_data"]
is_admin = current_user.get("is_admin", False)
allowed_ids = current_user.get("allowed_projects") or []

# --- 3. PROJECT RETRIEVAL ---
query = supabase.table("projects").select("*").order("project_code")
if not is_admin:
    query = query.in_("id", allowed_ids if allowed_ids else ['00000000-0000-0000-0000-000000000000'])
projects_list = query.execute().data

# --- 4. SIDEBAR ---
st.sidebar.title("🏗️ BIM Manager")
menu = st.sidebar.radio("Vai a:", ["📍 Locali", "🔗 Mappatura Parametri", "⚙️ Gestione Sistema"] if is_admin else ["📍 Locali", "🔗 Mappatura Parametri"])
if st.sidebar.button("🚪 Logout"):
    st.session_state["user_data"] = None
    st.rerun()

# --- 5. PAGE: ROOMS ---
if menu == "📍 Locali":
    if not projects_list:
        st.warning("Nessun progetto assegnato.")
    else:
        project_options = {f"{p['project_code']} - {p['project_name']}": p for p in projects_list}
        selected_label = st.selectbox("Seleziona Progetto:", list(project_options.keys()))
        project_id = project_options[selected_label]['id']

        maps_resp = supabase.table("parameter_mappings").select("db_column_name").eq("project_id", project_id).execute()
        mapped_params = [m['db_column_name'] for m in maps_resp.data]

        with st.expander("➕ Aggiunta Manuale Singolo Locale"):
            with st.form("manual_room"):
                c1, c2 = st.columns(2)
                new_num = c1.text_input("Numero Locale")
                new_name = c2.text_input("Nome Locale (Planned)")
                if st.form_submit_button("Aggiungi"):
                    if new_num:
                        payload = {"project_id": project_id, "room_number": new_num, "room_name_planned": new_name}
                        supabase.table("rooms").upsert(payload, on_conflict="project_id,room_number").execute()
                        st.rerun()

        with st.expander("📥 Import / Export Excel"):
            c1, c2 = st.columns(2)
            with c1:
                st.write("**Esporta Dati**")
                rooms_raw = supabase.table("rooms").select("*").eq("project_id", project_id).order("room_number").execute()
                export_data = []
                for r in rooms_raw.data:
                    row = {"Room Number": r["room_number"], "Room Name": r["room_name_planned"]}
                    p_json = r.get("parameters") or {}
                    for p in mapped_params: row[p] = p_json.get(p, "")
                    export_data.append(row)
                df_export = pd.DataFrame(export_data) if export_data else pd.DataFrame(columns=["Room Number", "Room Name"] + mapped_params)
                buf = io.BytesIO()
                with pd.ExcelWriter(buf, engine='xlsxwriter') as writer:
                    df_export.to_excel(writer, index=False)
                st.download_button("⬇️ Scarica Excel", data=buf.getvalue(), file_name=f"locali_{project_id}.xlsx")
            
            with c2:
                st.write("**Importa (Preserva Formato 01, 02)**")
                up_rooms = st.file_uploader("Carica Excel", type=["xlsx"])
                if up_rooms and st.button("🚀 Sincronizza nel Database"):
                    # LETTURA FORZATA COME STRINGA PER PRESERVARE GLI ZERI INIZIALI
                    df_up = pd.read_excel(up_rooms, dtype=str)
                    for _, row in df_up.iterrows():
                        r_num = str(row.get("Room Number", "")).strip()
                        if r_num.endswith('.0'): r_num = r_num[:-2] # Pulizia .0
                        
                        if r_num and r_num != "nan":
                            p_save = {}
                            for p in mapped_params:
                                if p in row and pd.notna(row[p]):
                                    val = str(row[p]).strip()
                                    if val.endswith('.0'): val = val[:-2] # Pulizia .0 sui parametri
                                    p_save[p] = val
                            
                            payload = {
                                "project_id": project_id, 
                                "room_number": r_num, 
                                "room_name_planned": str(row.get("Room Name", "")).strip(), 
                                "parameters": p_save
                            }
                            # Anti-duplicazione tramite upsert
                            supabase.table("rooms").upsert(payload, on_conflict="project_id,room_number").execute()
                    st.success("Database aggiornato correttamente!")
                    st.rerun()

        # Visualizzazione Tabella
        st.divider()
        rooms_resp = supabase.table("rooms").select("*").eq("project_id", project_id).order("room_number").execute()
        if rooms_resp.data:
            flat_data = []
            for r in rooms_resp.data:
                row = {"id": r["id"], "Numero": r["room_number"], "Nome": r["room_name_planned"]}
                p_json = r.get("parameters") or {}
                for p in mapped_params: row[p] = p_json.get(p, "")
                flat_data.append(row)
            st.data_editor(pd.DataFrame(flat_data), hide_index=True, use_container_width=True)

# --- 6. PAGE: PARAMETER MAPPING ---
elif menu == "🔗 Mappatura Parametri":
    project_options = {f"{p['project_code']} - {p['project_name']}": p for p in projects_list}
    selected_label = st.selectbox("Progetto:", list(project_options.keys()))
    project_id = project_options[selected_label]['id']

    with st.form("add_map"):
        c1, c2 = st.columns(2)
        db_p = c1.text_input("Database Parameter (es. 01_Finitura)")
        rv_p = c2.text_input("Revit Parameter (es. Wall Finish)")
        if st.form_submit_button("Aggiungi Mappatura"):
            if db_p and rv_p:
                supabase.table("parameter_mappings").insert({"project_id": project_id, "db_column_name": db_p, "revit_parameter_name": rv_p}).execute()
                st.rerun()

    maps = supabase.table("parameter_mappings").select("*").eq("project_id", project_id).execute().data
    if maps:
        df_maps = pd.DataFrame(maps)[["id", "db_column_name", "revit_parameter_name"]]
        st.table(df_maps)
        if st.button("Svuota Mappature"):
            supabase.table("parameter_mappings").delete().eq("project_id", project_id).execute()
            st.rerun()

# --- 7. PAGE: ADMIN ---
elif menu == "⚙️ Gestione Sistema" and is_admin:
    st.title("🛡️ Admin Dashboard")
    t1, t2 = st.tabs(["🏗️ Progetti", "👥 Utenti"])
    with t1:
        with st.form("new_p"):
            c1, c2 = st.columns(2)
            code = c1.text_input("Codice Progetto")
            name = c2.text_input("Nome Progetto")
            if st.form_submit_button("Crea Progetto"):
                supabase.table("projects").insert({"project_code": code, "project_name": name}).execute()
                st.rerun()
    with t2:
        email_new = st.text_input("Email da autorizzare")
        if st.button("Autorizza Utente"):
            supabase.table("user_permissions").insert({"email": email_new.lower(), "is_admin": False}).execute()
            st.rerun()
