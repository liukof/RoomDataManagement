import streamlit as st
import pandas as pd
from supabase import create_client, Client

# --- SETUP & AUTH ---
try:
    url = st.secrets["SUPABASE_URL"]
    key = st.secrets["SUPABASE_KEY"]
except KeyError:
    st.error("Missing Configuration in Secrets!")
    st.stop()

@st.cache_resource
def get_supabase_client() -> Client:
    return create_client(url, key)

supabase = get_supabase_client()

# --- SECURITY CHECK ---
user = st.session_state.get("user_data")
if not user or not user.get("is_admin"):
    st.error("🛑 Accesso riservato agli amministratori.")
    if st.button("Torna alla Home"):
        st.switch_page("app.py")
    st.stop()

st.title("⚙️ System Management")
st.sidebar.title("🏗️ Admin Panel")
st.sidebar.write(f"👤 Admin: **{user['email']}**")

t1, t2 = st.tabs(["🏗️ Projects Management", "👥 User Permissions"])

# --- TAB 1: PROJECTS MANAGEMENT ---
with t1:
    st.subheader("Create New Project")
    with st.form("new_project_form"):
        c1, c2 = st.columns(2)
        pc = c1.text_input("Project Code", placeholder="e.g. PRJ-001")
        pn = c2.text_input("Project Name", placeholder="e.g. New Hospital Wing")
        if st.form_submit_button("🚀 Create Project", use_container_width=True):
            if pc and pn:
                try:
                    supabase.table("projects").insert({"project_code": pc, "project_name": pn}).execute()
                    st.success(f"Project {pc} created!")
                    st.rerun()
                except Exception as e:
                    st.error(f"Error: {e}")
            else:
                st.warning("Please fill all fields.")

    st.divider()
    st.subheader("Existing Projects")
    all_projects = supabase.table("projects").select("*").order("project_code").execute().data
    
    if all_projects:
        dfp = pd.DataFrame(all_projects)[["id", "project_code", "project_name"]]
        dfp.insert(0, "Select", False)
        
        # Editor per rinominare o selezionare per eliminazione
        edp = st.data_editor(
            dfp, 
            use_container_width=True, 
            hide_index=True, 
            column_config={"id": None, "Select": st.column_config.CheckboxColumn("Select")}
        )
        
        cs, cd = st.columns(2)
        if cs.button("💾 Save Renames", use_container_width=True):
            for _, r in edp.iterrows():
                supabase.table("projects").update({
                    "project_code": r["project_code"], 
                    "project_name": r["project_name"]
                }).eq("id", int(r["id"])).execute()
            st.success("Changes saved!")
            st.rerun()
            
        if cd.button("🗑️ Delete Selected Projects", type="primary", use_container_width=True):
            selected_ids = [int(r["id"]) for _, r in edp[edp["Select"] == True].iterrows()]
            if selected_ids:
                supabase.table("projects").delete().in_("id", selected_ids).execute()
                st.success(f"Deleted {len(selected_ids)} projects.")
                st.rerun()
    else:
        st.info("No projects found.")

# --- TAB 2: USERS & PERMISSIONS ---
with t2:
    st.subheader("Authorize New User")
    with st.form("new_user_form"):
        new_email = st.text_input("User Email").lower().strip()
        is_new_admin = st.checkbox("Grant Admin Privileges")
        if st.form_submit_button("➕ Authorize User"):
            if "@" in new_email:
                supabase.table("user_permissions").insert({
                    "email": new_email, 
                    "is_admin": is_new_admin
                }).execute()
                st.success(f"User {new_email} authorized.")
                st.rerun()
            else:
                st.error("Invalid email address.")

    st.divider()
    st.subheader("Project Assignment")
    users = supabase.table("user_permissions").select("*").execute().data
    
    if users and all_projects:
        # Mappa nomi progetti -> ID
        p_map = {f"{p['project_code']}": int(p['id']) for p in all_projects}
        p_inv_map = {int(p['id']): f"{p['project_code']}" for p in all_projects}
        
        u_to_ed = st.selectbox("Select User to edit permissions:", [u['email'] for u in users])
        curr_u = next(u for u in users if u['email'] == u_to_ed)
        
        # Recupera ID correnti e converti in label per il multiselect
        curr_ids = [int(x) for x in (curr_u.get("allowed_projects") or [])]
        curr_labels = [p_inv_map[pid] for pid in curr_ids if pid in p_inv_map]
        
        sel_p = st.multiselect("Allowed Projects for this user:", list(p_map.keys()), default=curr_labels)
        
        if st.button("💾 Update User Permissions", use_container_width=True):
            new_ids = [int(p_map[p]) for p in sel_p]
            supabase.table("user_permissions").update({
                "allowed_projects": new_ids
            }).eq("email", u_to_ed).execute()
            st.success(f"Permissions updated for {u_to_ed}!")
            st.rerun()
            
    st.divider()
    st.subheader("Users List")
    if users:
        df_u = pd.DataFrame(users)[["email", "is_admin", "allowed_projects"]]
        df_u.insert(0, "Select", False)
        ed_u = st.data_editor(df_u, use_container_width=True, hide_index=True)
        
        if st.button("🗑️ Revoke Access for Selected Users"):
            emails_to_del = ed_u[ed_u["Select"] == True]["email"].tolist()
            if emails_to_del:
                supabase.table("user_permissions").delete().in_("email", emails_to_del).execute()
                st.rerun()
