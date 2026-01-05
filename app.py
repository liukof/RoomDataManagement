import streamlit as st
import pandas as pd
from supabase import create_client, Client
import io

# --- 1. SUPABASE SETUP ---
try:
    url = st.secrets["SUPABASE_URL"]
    key = st.secrets["SUPABASE_KEY"]
except:
    st.error("Missing Configuration in Secrets! (SUPABASE_URL, SUPABASE_KEY)")
    st.stop()

@st.cache_resource
def get_supabase_client():
    return create_client(url, key)

supabase: Client = get_supabase_client()

st.set_page_config(page_title="BIM Data Manager PRO", layout="wide", page_icon="🏗️")

# --- 2. AUTHENTICATION LOGIC ---
if "user_data" not in st.session_state:
    st.session_state["user_data"] = None

if st.session_state["user_data"] is None:
    st.title("🏗️ BIM Data Manager - Login")
    with st.form("login_form"):
        email_input = st.text_input("Email Address", placeholder="name@company.com").lower().strip()
        submit_login = st.form_submit_button("Login", use_container_width=True, type="primary")
    if submit_login:
        res = supabase.table("user_permissions").select("*").eq("email", email_input).execute()
        if res.data:
            st.session_state["user_data"] = res.data[0]
            st.rerun()
        else:
            st.error("User not authorized.")
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
st.sidebar.write(f"👤 **{current_user['email']}**")
menu_options = ["📍 Rooms", "🔗 Parameter Mapping"]
if is_admin:
    menu_options.append("⚙️ System Management")

menu = st.sidebar.radio("Go to:", menu_options)

if st.sidebar.button("🚪 Logout"):
    st.session_state["user_data"] = None
    st.rerun()

# --- 5. PAGE: ROOMS ---
if menu == "📍 Rooms":
    if not projects_list:
        st.warning("No projects assigned.")
    else:
        project_options = {f"{p['project_code']} - {p['project_name']}": p for p in projects_list}
        selected_label = st.selectbox("Select Project:", list(project_options.keys()))
        project_id = project_options[selected_label]['id']

        maps_resp = supabase.table("parameter_mappings").select("db_column_name").eq("project_id", project_id).execute()
        mapped_params = [m['db_column_name'] for m in maps_resp.data]

        with st.expander("➕ Add Single Room Manually"):
            with st.form("manual_room"):
                c1, c2 = st.columns(2)
                new_num = c1.text_input("Room Number")
                new_name = c2.text_input("Room Name (Planned)")
                if st.form_submit_button("Add Room"):
                    if new_num:
                        payload = {"project_id": project_id, "room_number": new_num, "room_name_planned": new_name}
                        supabase.table("rooms").upsert(payload, on_conflict="project_id,room_number").execute()
                        st.success(f"Room {new_num} updated.")
                        st.rerun()

        with st.expander("📥 Import / Export / Reset Rooms"):
            c1, c2, c3 = st.columns(3)
            with c1:
                st.write("**Export Rooms**")
                rooms_raw = supabase.table("rooms").select("*").eq("project_id", project_id).order("room_number").execute()
                export_data = []
                for r in rooms_raw.data:
                    row = {"Room Number": r["room_number"], "Room Name": r["room_name_planned"]}
                    p_json = r.get("parameters") or {}
                    for p in mapped_params: row[p] = p_json.get(p, "")
                    export_data.append(row)
                df_export = pd.DataFrame(export_data)
                buf = io.BytesIO()
                with pd.ExcelWriter(buf, engine='xlsxwriter') as writer:
                    df_export.to_excel(writer, index=False)
                st.download_button("⬇️ Download Rooms Excel", data=buf.getvalue(), file_name=f"rooms_{project_id}.xlsx")
            
            with c2:
                st.write("**Import Rooms (Bulk Sync)**")
                up_rooms = st.file_uploader("Upload Rooms Excel", type=["xlsx"], key="up_rooms")
                if up_rooms and st.button("🚀 Sync Rooms"):
                    df_up = pd.read_excel(up_rooms, dtype=str)
                    bulk_data = []
                    for _, row in df_up.iterrows():
                        r_num = str(row.get("Room Number", "")).strip()
                        if r_num.endswith('.0'): r_num = r_num[:-2]
                        if r_num and r_num != "nan":
                            p_save = {}
                            for p in mapped_params:
                                if p in row and pd.notna(row[p]):
                                    val = str(row[p]).strip()
                                    if val.endswith('.0'): val = val[:-2]
                                    p_save[p] = val
                            bulk_data.append({
                                "project_id": project_id, 
                                "room_number": r_num, 
                                "room_name_planned": str(row.get("Room Name", "")).strip(), 
                                "parameters": p_save
                            })
                    if bulk_data:
                        supabase.table("rooms").upsert(bulk_data, on_conflict="project_id,room_number").execute()
                        st.success("Rooms Updated!")
                        st.rerun()

            with c3:
                st.write("**Danger Zone**")
                if st.button("🗑️ DELETE ALL ROOMS"):
                    supabase.table("rooms").delete().eq("project_id", project_id).execute()
                    st.rerun()

        st.divider()
        rooms_resp = supabase.table("rooms").select("*").eq("project_id", project_id).order("room_number").execute()
        if rooms_resp.data:
            flat_data = []
            for r in rooms_resp.data:
                updated_at = r.get("updated_at", "N/A").split(".")[0].replace("T", " ")
                row = {"id": r["id"], "Number": r["room_number"], "Name": r["room_name_planned"], "DB_Updated": updated_at}
                p_json = r.get("parameters") or {}
                for p in mapped_params: row[p] = p_json.get(p, "")
                flat_data.append(row)
            
            df_rooms = pd.DataFrame(flat_data)
            df_rooms["Delete"] = False
            edited_df = st.data_editor(df_rooms, column_config={"id": None, "DB_Updated": st.column_config.TextColumn("Last Edit (DB)", disabled=True)}, use_container_width=True, hide_index=True, key="ed_rooms")
            
            b1, b2 = st.columns(2)
            if b1.button("💾 SAVE CHANGES", use_container_width=True, type="primary"):
                for _, row in edited_df.iterrows():
                    up_p = {p: row[p] for p in mapped_params if p in row}
                    supabase.table("rooms").update({"room_name_planned": row["Name"], "parameters": up_p}).eq("id", row["id"]).execute()
                st.rerun()
            if b2.button("🗑️ DELETE SELECTED ROOMS", use_container_width=True):
                for _, r in edited_df[edited_df["Delete"] == True].iterrows():
                    supabase.table("rooms").delete().eq("id", r["id"]).execute()
                st.rerun()

# --- 6. PAGE: PARAMETER MAPPING ---
elif menu == "🔗 Parameter Mapping":
    project_options = {f"{p['project_code']} - {p['project_name']}": p for p in projects_list}
    selected_label = st.selectbox("Select Project:", list(project_options.keys()))
    project_id = project_options[selected_label]['id']

    with st.expander("➕ Add Single Mapping Manually"):
        with st.form("single_map"):
            c1, c2 = st.columns(2)
            db_v = c1.text_input("Database Column Name (e.g., 01_Department)")
            rv_v = c2.text_input("Revit Parameter Name (e.g., Department)")
            if st.form_submit_button("Add Mapping"):
                if db_v and rv_v:
                    supabase.table("parameter_mappings").insert({"project_id": project_id, "db_column_name": db_v, "revit_parameter_name": rv_v}).execute()
                    st.rerun()

    with st.expander("📥 Import / Export / Reset Mappings"):
        c1, c2, c3 = st.columns(3)
        with c1:
            st.write("**Export Mappings**")
            maps_raw = supabase.table("parameter_mappings").select("*").eq("project_id", project_id).execute().data
            if maps_raw:
                df_maps_exp = pd.DataFrame(maps_raw)[["db_column_name", "revit_parameter_name"]]
                buf_m = io.BytesIO()
                with pd.ExcelWriter(buf_m, engine='xlsxwriter') as writer:
                    df_maps_exp.to_excel(writer, index=False)
                st.download_button("⬇️ Download Mapping Excel", data=buf_m.getvalue(), file_name=f"mappings_{project_id}.xlsx")
        
        with c2:
            st.write("**Import Mappings (Bulk)**")
            up_maps = st.file_uploader("Upload Mapping Excel", type=["xlsx"], key="up_maps")
            if up_maps and st.button("🚀 Upload Mappings"):
                df_m_up = pd.read_excel(up_maps, dtype=str)
                m_bulk = []
                for _, row in df_m_up.iterrows():
                    db_col = str(row.get("db_column_name", "")).strip()
                    rv_param = str(row.get("revit_parameter_name", "")).strip()
                    if db_col and rv_param:
                        m_bulk.append({
                            "project_id": project_id,
                            "db_column_name": db_col,
                            "revit_parameter_name": rv_param
                        })
                if m_bulk:
                    # Usiamo upsert per evitare duplicati se i nomi sono uguali
                    supabase.table("parameter_mappings").upsert(m_bulk, on_conflict="project_id,db_column_name").execute()
                    st.success("Mappings Updated!")
                    st.rerun()

        with c3:
            st.write("**Danger Zone**")
            if st.button("🗑️ RESET ALL MAPPINGS"):
                supabase.table("parameter_mappings").delete().eq("project_id", project_id).execute()
                st.rerun()

    st.divider()
    maps = supabase.table("parameter_mappings").select("*").eq("project_id", project_id).execute().data
    if maps:
        df_m = pd.DataFrame(maps)[["id", "db_column_name", "revit_parameter_name"]]
        df_m["Delete"] = False
        ed_m = st.data_editor(df_m, column_config={"id": None}, use_container_width=True, hide_index=True, key="ed_maps")
        if st.button("🗑️ DELETE SELECTED MAPPINGS", type="primary"):
            for _, r in ed_m[ed_m["Delete"] == True].iterrows():
                supabase.table("parameter_mappings").delete().eq("id", r["id"]).execute()
            st.rerun()

# --- 7. PAGE: SYSTEM MANAGEMENT ---
elif menu == "⚙️ System Management" and is_admin:
    st.title("🛡️ Admin Dashboard")
    t1, t2, t3 = st.tabs(["🏗️ Projects", "👥 Users", "🔗 Access Control"])
    with t1:
        with st.form("new_p"):
            cp_val = st.text_input("Project Code")
            np_val = st.text_input("Project Name")
            if st.form_submit_button("Create Project"):
                if cp_val and np_val:
                    supabase.table("projects").insert({"project_code": cp_val, "project_name": np_val}).execute()
                    st.rerun()
    with t2:
        email_new = st.text_input("Authorize New Email")
        if st.button("Add User"):
            supabase.table("user_permissions").insert({"email": email_new.lower(), "is_admin": False}).execute()
            st.rerun()
    with t3:
        all_users_resp = supabase.table("user_permissions").select("*").eq("is_admin", False).execute()
        all_projects_resp = supabase.table("projects").select("*").order("project_code").execute()
        if all_users_resp.data and all_projects_resp.data:
            u_emails = [u['email'] for u in all_users_resp.data]
            u_target_email = st.selectbox("Select User:", u_emails)
            selected_user = next(u for u in all_users_resp.data if u['email'] == u_target_email)
            proj_mapping = {f"{p['project_code']} - {p['project_name']}": p['id'] for p in all_projects_resp.data}
            current_allowed_ids = selected_user.get('allowed_projects') or []
            current_labels = [l for l, p_id in proj_mapping.items() if p_id in current_allowed_ids]
            new_selection_labels = st.multiselect("Assign Projects:", list(proj_mapping.keys()), default=current_labels)
            if st.button("💾 Save Access Rights"):
                new_ids = [proj_mapping[label] for label in new_selection_labels]
                supabase.table("user_permissions").update({"allowed_projects": new_ids}).eq("id", selected_user['id']).execute()
                st.success("Permissions updated!")
                st.rerun()
