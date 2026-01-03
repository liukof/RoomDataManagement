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

# --- 2. AUTHENTICATION LOGIC (Email Whitelist) ---
if "user_data" not in st.session_state:
    st.session_state["user_data"] = None

def logout():
    st.session_state["user_data"] = None
    st.rerun()

if st.session_state["user_data"] is None:
    st.title("🏗️ BIM Data Manager - Login")
    st.markdown("### Access with Corporate Email")
    
    with st.form("login_form"):
        email_input = st.text_input("Email Address", placeholder="name@company.com").lower().strip()
        submit_login = st.form_submit_button("Login", use_container_width=True, type="primary")
    
    if submit_login:
        if email_input:
            res = supabase.table("user_permissions").select("*").eq("email", email_input).execute()
            if res.data and len(res.data) > 0:
                st.session_state["user_data"] = res.data[0]
                st.success(f"Welcome {email_input}!")
                st.rerun()
            else:
                st.error("🚫 User not registered")
                st.info(f"The email **{email_input}** is not in the whitelist. Please contact the administrator.")
        else:
            st.warning("⚠️ Please enter an email address.")
    st.stop()

# Session User Data
current_user = st.session_state["user_data"]
is_admin = current_user.get("is_admin", False)
allowed_project_ids = current_user.get("allowed_projects") or []

# --- 3. PROJECT RETRIEVAL ---
try:
    query = supabase.table("projects").select("*").order("project_code")
    if not is_admin:
        valid_ids = allowed_project_ids if allowed_project_ids else ['00000000-0000-0000-0000-000000000000']
        query = query.in_("id", valid_ids)
    projects_list = query.execute().data
except Exception as e:
    st.error(f"Database error: {e}")
    st.stop()

# --- 4. SIDEBAR ---
st.sidebar.title("🏗️ BIM Manager")
st.sidebar.write(f"👤 **{current_user['email']}**")
if is_admin: st.sidebar.info("Role: ADMINISTRATOR")

menu_opt = ["📍 Rooms", "🔗 Parameter Mapping"]
if is_admin: menu_opt.append("⚙️ System Management")

menu = st.sidebar.radio("Go to:", menu_opt)

if st.sidebar.button("🚪 Logout"):
    logout()

# --- 5. PAGE: ROOMS ---
if menu == "📍 Rooms":
    if not projects_list:
        st.warning("No projects assigned to you. Contact the admin.")
    else:
        project_options = {f"{p['project_code']} - {p['project_name']}": p for p in projects_list}
        selected_label = st.selectbox("Select Project:", list(project_options.keys()))
        project_id = project_options[selected_label]['id']

        maps_resp = supabase.table("parameter_mappings").select("db_column_name").eq("project_id", project_id).execute()
        mapped_params = [m['db_column_name'] for m in maps_resp.data]

        with st.expander("📥 Import / Export / Reset Rooms"):
            c1, c2, c3 = st.columns(3)
            with c1:
                st.write("**Export**")
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
                st.download_button("⬇️ Download Excel", data=buf.getvalue(), file_name=f"rooms_{project_id}.xlsx")
            
            with c2:
                st.write("**Import (Upsert)**")
                up_rooms = st.file_uploader("Upload Excel", type=["xlsx"], key="up_loc")
                if up_rooms and st.button("🚀 Sync Data"):
                    df_up = pd.read_excel(up_rooms)
                    for _, row in df_up.iterrows():
                        r_num = str(row.get("room_number", "")).strip()
                        if r_num and r_num != "nan":
                            p_save = {p: str(row[p]) for p in mapped_params if p in row and pd.notna(row[p])}
                            exist = supabase.table("rooms").select("id").eq("project_id", project_id).eq("room_number", r_num).execute()
                            payload = {"project_id": project_id, "room_number": r_num, "room_name_planned": str(row.get("room_name_planned", "")), "parameters": p_save}
                            if exist.data: supabase.table("rooms").update(payload).eq("id", exist.data[0]["id"]).execute()
                            else: supabase.table("rooms").insert(payload).execute()
                    st.success("Data synchronized!")
                    st.rerun()
            
            with c3:
                st.write("**Danger Zone**")
                if st.button("🗑️ DELETE ALL ROOMS", type="secondary"):
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
            df_rooms["Delete"] = False
            
            st.subheader("📝 Data Editor")
            edited_df = st.data_editor(
                df_rooms, 
                column_config={
                    "id": None, 
                    "room_number": st.column_config.TextColumn("Number", disabled=True),
                    "Delete": st.column_config.CheckboxColumn("Sel.")
                }, 
                use_container_width=True, 
                hide_index=True,
                key="editor_rooms"
            )
            
            col_b1, col_b2 = st.columns(2)
            if col_b1.button("💾 SAVE CHANGES", use_container_width=True, type="primary"):
                for _, row in edited_df.iterrows():
                    up_p = {p: row[p] for p in mapped_params if p in row}
                    supabase.table("rooms").update({"room_name_planned": row["room_name_planned"], "parameters": up_p}).eq("id", row["id"]).execute()
                st.success("Changes saved!")
                st.rerun()
                
            if col_b2.button("🗑️ DELETE SELECTED ROWS", use_container_width=True):
                rows_to_del = edited_df[edited_df["Delete"] == True]
                if not rows_to_del.empty:
                    for _, r in rows_to_del.iterrows():
                        supabase.table("rooms").delete().eq("id", r["id"]).execute()
                    st.rerun()
                else:
                    st.warning("Please select at least one row.")
        else:
            st.info("No rooms found for this project.")

# --- 6. PAGE: PARAMETER MAPPING ---
elif menu == "🔗 Parameter Mapping":
    project_options = {f"{p['project_code']} - {p['project_name']}": p for p in projects_list}
    selected_label = st.selectbox("Select Project:", list(project_options.keys()))
    project_id = project_options[selected_label]['id']

    st.subheader("Mappping")
    
    with st.expander("📥 Import / Export Mappings"):
        cm1, cm2 = st.columns(2)
        with cm1:
            res_m = supabase.table("parameter_mappings").select("*").eq("project_id", project_id).execute()
            df_m_exp = pd.DataFrame(res_m.data)[["db_column_name", "revit_parameter_name"]] if res_m.data else pd.DataFrame(columns=["Database Parameter", "Revit Parameter"])
            df_m_exp.columns = ["Database Parameter", "Revit Parameter"]
            buf_m = io.BytesIO()
            with pd.ExcelWriter(buf_m, engine='xlsxwriter') as writer:
                df_m_exp.to_excel(writer, index=False)
            st.download_button("⬇️ Download Template", data=buf_m.getvalue(), file_name="parameter_mapping_template.xlsx")
        with cm2:
            up_m = st.file_uploader("Upload Mappings Excel", type=["xlsx"], key="up_map")
            if up_m and st.button("🚀 Upload Mappings"):
                df_m_up = pd.read_excel(up_m)
                # Ensure the columns match the updated template names
                batch = [{"project_id": project_id, "db_column_name": str(r['Database Parameter']).strip(), "revit_parameter_name": str(r['Revit Parameter']).strip()} for _, r in df_m_up.dropna().iterrows()]
                if batch:
                    supabase.table("parameter_mappings").insert(batch).execute()
                    st.rerun()

    with st.form("single_map"):
        st.write("**Add Single Mapping**")
        c1, c2 = st.columns(2)
        db_v = c1.text_input("Database Parameter (e.g. Wall_Finish)")
        rv_v = c2.text_input("Revit Parameter (e.g. Wall Finish)")
        if st.form_submit_button("Add Mapping"):
            if db_v and rv_v:
                supabase.table("parameter_mappings").insert({"project_id": project_id, "db_column_name": db_v, "revit_parameter_name": rv_v}).execute()
                st.rerun()

    res_map = supabase.table("parameter_mappings").select("*").eq("project_id", project_id).execute()
    if res_map.data:
        df_m = pd.DataFrame(res_map.data)
        df_m["Delete"] = False
        ed_m = st.data_editor(
            df_m[["id", "db_column_name", "revit_parameter_name", "Delete"]], 
            column_config={
                "id": None,
                "db_column_name": "Database Parameter",
                "revit_parameter_name": "Revit Parameter"
            }, 
            use_container_width=True, hide_index=True, key="ed_map"
        )
        if st.button("🗑️ Remove Selected Mappings"):
            for _, r in ed_m[ed_m["Delete"] == True].iterrows():
                supabase.table("parameter_mappings").delete().eq("id", r["id"]).execute()
            st.rerun()

# --- 7. SYSTEM MANAGEMENT (ADMIN ONLY) ---
elif menu == "⚙️ System Management" and is_admin:
    st.title("🛡️ Admin Dashboard")
    t1, t2, t3 = st.tabs(["🏗️ Projects", "👥 User Whitelist", "🔗 Access Control"])

    with t1:
        st.subheader("New Project")
        with st.form("new_project"):
            cp = st.text_input("Project Code")
            np = st.text_input("Project Name")
            if st.form_submit_button("Create"):
                if cp and np:
                    supabase.table("projects").insert({"project_code": cp, "project_name": np}).execute()
                    st.rerun()

        st.divider()
        st.subheader("Existing Projects")
        all_p = supabase.table("projects").select("*").order("project_code").execute().data
        if all_p:
            df_p = pd.DataFrame(all_p)[["id", "project_code", "project_name"]]
            df_p["Delete"] = False
            ed_p = st.data_editor(df_p, column_config={"id": None}, use_container_width=True, hide_index=True, key="ed_pro")
            
            c_p1, c_p2 = st.columns(2)
            if c_p1.button("💾 Save Project Names"):
                for _, r in ed_p.iterrows():
                    supabase.table("projects").update({"project_code": r["project_code"], "project_name": r["project_name"]}).eq("id", r["id"]).execute()
                st.rerun()
            if c_p2.button("🔥 Delete Selected Projects"):
                for _, r in ed_p[ed_p["Delete"] == True].iterrows():
                    supabase.table("projects").delete().eq("id", r["id"]).execute()
                st.rerun()

    with t2:
        st.subheader("Authorize New User")
        with st.form("new_user"):
            em = st.text_input("User Email").lower().strip()
            ad = st.checkbox("Is Admin?")
            if st.form_submit_button("Add to Whitelist"):
                if em:
                    supabase.table("user_permissions").insert({"email": em, "is_admin": ad, "allowed_projects": []}).execute()
                    st.rerun()
        
        all_u = supabase.table("user_permissions").select("*").execute().data
        if all_u:
            st.table(pd.DataFrame(all_u)[["email", "is_admin"]])

    with t3:
        st.subheader("Assign Projects to Collaborators")
        all_u_list = supabase.table("user_permissions").select("*").eq("is_admin", False).execute().data
        all_p_list = supabase.table("projects").select("*").execute().data
        
        if all_u_list and all_p_list:
            target = st.selectbox("Select User:", [u['email'] for u in all_u_list])
            u_data = next(u for u in all_u_list if u['email'] == target)
            
            p_map = {f"{p['project_code']}": p['id'] for p in all_p_list}
            current_ids = u_data.get('allowed_projects') or []
            current_codes = [p['project_code'] for p in all_p_list if p['id'] in current_ids]
            
            new_sel = st.multiselect("Authorized Projects:", list(p_map.keys()), default=current_codes)
            
            if st.button("💾 Update Access Rights"):
                new_ids = [p_map[code] for code in new_sel]
                supabase.table("user_permissions").update({"allowed_projects": new_ids}).eq("email", target).execute()
                st.success(f"Access updated for {target}!")
                st.rerun()

