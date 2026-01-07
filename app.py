import streamlit as st
import pandas as pd
from supabase import create_client, Client
import io

# --- 1. SUPABASE SETUP ---
try:
    url = st.secrets["SUPABASE_URL"]
    key = st.secrets["SUPABASE_KEY"]
except:
    st.error("Missing Configuration in Secrets!")
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
        email_input = st.text_input("Email Address").lower().strip()
        if st.form_submit_button("Login", use_container_width=True, type="primary"):
            res = supabase.table("user_permissions").select("*").eq("email", email_input).execute()
            if res.data:
                st.session_state["user_data"] = res.data[0]
                st.rerun()
            else: st.error("User not authorized.")
    st.stop()

current_user = st.session_state["user_data"]
is_admin = current_user.get("is_admin", False)
# Forziamo allowed_ids a essere una lista di int
allowed_ids = [int(i) for i in (current_user.get("allowed_projects") or [])]

# --- 3. PROJECT SELECTION ---
query = supabase.table("projects").select("*").order("project_code")
if not is_admin:
    query = query.in_("id", allowed_ids if allowed_ids else [0])
projects_list = query.execute().data

# --- 4. SIDEBAR ---
st.sidebar.title("🏗️ BIM Manager")
st.sidebar.write(f"👤 **{current_user['email']}**")
menu = st.sidebar.radio("Go to:", ["📍 Rooms & Item Lists", "📦 Item Catalog", "🔗 Parameter Mapping", "⚙️ System Management"] if is_admin else ["📍 Rooms & Item Lists", "📦 Item Catalog", "🔗 Parameter Mapping"])

if st.sidebar.button("🚪 Logout"):
    st.session_state["user_data"] = None
    st.rerun()

# --- GLOBAL PROJECT CONTEXT ---
project_id = None
if projects_list:
    project_options = {f"{p['project_code']} - {p['project_name']}": p for p in projects_list}
    selected_label = st.selectbox("Current Project Context:", list(project_options.keys()))
    project_id = int(project_options[selected_label]['id'])

# --- 5. PAGE: ROOMS & ITEM LISTS ---
if menu == "📍 Rooms & Item Lists":
    if not project_id: st.info("Create a project in System Management first."); st.stop()
    
    maps_resp = supabase.table("parameter_mappings").select("db_column_name").eq("project_id", project_id).execute()
    mapped_params = [m['db_column_name'] for m in maps_resp.data]

    with st.expander("📥 Import / Export Rooms"):
        c1, c2 = st.columns(2)
        with c1:
            st.write("**Export Rooms**")
            rooms_raw = supabase.table("rooms").select("*").eq("project_id", project_id).order("room_number").execute()
            if rooms_raw.data:
                df_exp = pd.DataFrame([{"Number": r["room_number"], "Name": r["room_name_planned"], **(r.get("parameters") or {})} for r in rooms_raw.data])
                buf = io.BytesIO()
                with pd.ExcelWriter(buf, engine='xlsxwriter') as writer: df_exp.to_excel(writer, index=False)
                st.download_button("⬇️ Download Excel", data=buf.getvalue(), file_name="rooms_export.xlsx")
        with c2:
            st.write("**Import Rooms**")
            up_file = st.file_uploader("Upload XLSX", type=["xlsx"], key="up_rooms")
            if up_file and st.button("🚀 Sync Rooms"):
                df_up = pd.read_excel(up_file, dtype=str)
                bulk_data = [{"project_id": project_id, "room_number": str(row["Number"]).strip(), "room_name_planned": str(row["Name"]), "parameters": {p: row[p] for p in mapped_params if p in row and pd.notna(row[p])}} for _, row in df_up.iterrows()]
                supabase.table("rooms").upsert(bulk_data, on_conflict="project_id,room_number").execute()
                st.success("Rooms Updated!"); st.rerun()

    st.divider()
    cf1, cf2 = st.columns([2, 1])
    search_q = cf1.text_input("🔍 Filter (Number or Name)", placeholder="e.g. degenza")
    
    rooms_resp = supabase.table("rooms").select("*").eq("project_id", project_id).order("room_number").execute()
    if rooms_resp.data:
        flat_data = []
        for r in rooms_resp.data:
            row = {"id": int(r["id"]), "Number": r["room_number"], "Name": r["room_name_planned"]}
            p_json = r.get("parameters") or {}
            for p in mapped_params: row[p] = p_json.get(p, "")
            flat_data.append(row)
        df = pd.DataFrame(flat_data)
        
        mask = df.apply(lambda x: x.astype(str).str.contains(search_q, case=False).any(), axis=1) if search_q else [True]*len(df)
        df_filtered = df[mask].copy()
        df_filtered.insert(0, "Select", False)

        st.write(f"### 📍 Rooms List ({len(df_filtered)})")
        ed_rooms = st.data_editor(df_filtered, use_container_width=True, hide_index=True, column_config={"id": None})
        
        col_del1, col_del2 = st.columns(2)
        if col_del1.button("🗑️ DELETE SELECTED ROOMS", use_container_width=True):
            ids_to_del = [int(i) for i in ed_rooms[ed_rooms["Select"] == True]["id"].tolist()]
            if ids_to_del:
                supabase.table("rooms").delete().in_("id", ids_to_del).execute(); st.rerun()

        if col_del2.button("⚠️ DELETE ALL PROJECT ROOMS", type="primary", use_container_width=True):
            supabase.table("rooms").delete().eq("project_id", project_id).execute(); st.rerun()

        # --- BULK ITEM ADD ---
        st.divider()
        st.subheader("📦 Bulk Item Assignment")
        catalog = supabase.table("items").select("*").eq("project_id", project_id).execute().data
        if catalog:
            item_opt = {f"{i['item_code']} - {i['item_description']}": int(i['id']) for i in catalog}
            with st.form("bulk_item"):
                col1, col2 = st.columns([3, 1])
                t_item = col1.selectbox("Item to add to ALL rooms shown above:", list(item_opt.keys()))
                t_qty = col2.number_input("Qty", min_value=1, value=1)
                if st.form_submit_button("🚀 Add to Filtered Set"):
                    bulk = [{"room_id": int(r_id), "item_id": item_opt[t_item], "quantity": int(t_qty)} for r_id in df_filtered['id'].tolist()]
                    supabase.table("room_items").insert(bulk).execute(); st.rerun()

# --- 6. PAGE: ITEM CATALOG ---
elif menu == "📦 Item Catalog":
    if not project_id: st.stop()
    st.header("📦 Item Catalog Management")
    with st.expander("➕ Add Single Item"):
        with st.form("new_item"):
            i_c, i_d = st.text_input("Item Code"), st.text_input("Description")
            if st.form_submit_button("Save Item"):
                if i_c: supabase.table("items").insert({"project_id": project_id, "item_code": i_c, "item_description": i_d}).execute(); st.rerun()

    items_data = supabase.table("items").select("*").eq("project_id", project_id).execute().data
    if items_data:
        df_items = pd.DataFrame(items_data).drop(columns=['project_id'])
        df_items.insert(0, "Select", False)
        ed_cat = st.data_editor(df_items, use_container_width=True, hide_index=True, column_config={"id": None})
        if st.button("🗑️ Delete Selected Items"):
            ids_cat = [int(i) for i in ed_cat[ed_cat["Select"] == True]["id"].tolist()]
            if ids_cat: supabase.table("items").delete().in_("id", ids_cat).execute(); st.rerun()

# --- 7. PAGE: PARAMETER MAPPING ---
elif menu == "🔗 Parameter Mapping":
    if not project_id: st.stop()
    st.header("🔗 Parameter Mapping")
    with st.expander("📥 Import / Export Mappings"):
        c1, c2 = st.columns(2)
        with c1:
            maps_raw = supabase.table("parameter_mappings").select("*").eq("project_id", project_id).execute().data
            if maps_raw:
                df_m_exp = pd.DataFrame(maps_raw)[["db_column_name", "revit_parameter_name"]]
                buf = io.BytesIO()
                with pd.ExcelWriter(buf, engine='xlsxwriter') as writer: df_m_exp.to_excel(writer, index=False)
                st.download_button("⬇️ Download Mapping Excel", data=buf.getvalue(), file_name="mappings.xlsx")
        with c2:
            up_m = st.file_uploader("Upload Mappings XLSX", type=["xlsx"])
            if up_m and st.button("🚀 Upload Mappings"):
                df_m_up = pd.read_excel(up_m, dtype=str)
                m_bulk = [{"project_id": project_id, "db_column_name": str(row["db_column_name"]), "revit_parameter_name": str(row["revit_parameter_name"])} for _, row in df_m_up.iterrows()]
                supabase.table("parameter_mappings").upsert(m_bulk, on_conflict="project_id,db_column_name").execute(); st.rerun()

    with st.form("map_f"):
        db_p, rv_p = st.text_input("DB Param"), st.text_input("Revit Param")
        if st.form_submit_button("Add Single Mapping"):
            if db_p and rv_p: supabase.table("parameter_mappings").insert({"project_id": project_id, "db_column_name": db_p, "revit_parameter_name": rv_p}).execute(); st.rerun()
            
    maps = supabase.table("parameter_mappings").select("*").eq("project_id", project_id).execute().data
    if maps:
        df_m = pd.DataFrame(maps)[["id", "db_column_name", "revit_parameter_name"]]
        df_m.insert(0, "Select", False)
        ed_m = st.data_editor(df_m, use_container_width=True, hide_index=True, column_config={"id": None})
        if st.button("🗑️ Delete Selected Mappings"):
            ids_m = [int(i) for i in ed_m[ed_m["Select"] == True]["id"].tolist()]
            if ids_m: supabase.table("parameter_mappings").delete().in_("id", ids_m).execute(); st.rerun()

# --- 8. PAGE: SYSTEM MANAGEMENT ---
elif menu == "⚙️ System Management" and is_admin:
    st.header("⚙️ Admin Panel")
    t1, t2 = st.tabs(["🏗️ Projects", "👥 Users"])
    with t1:
        with st.form("new_p"):
            p_c, p_n = st.text_input("New Code"), st.text_input("New Name")
            if st.form_submit_button("Create Project"):
                supabase.table("projects").insert({"project_code": p_c, "project_name": p_n}).execute(); st.rerun()
        st.divider()
        df_p = pd.DataFrame(supabase.table("projects").select("*").execute().data)[["id", "project_code", "project_name"]]
        df_p.insert(0, "Select", False)
        ed_p = st.data_editor(df_p, use_container_width=True, hide_index=True, column_config={"id": None})
        c_save, c_del = st.columns(2)
        if c_save.button("💾 SAVE CHANGES (RENAME)", use_container_width=True):
            for _, r in ed_p.iterrows():
                supabase.table("projects").update({"project_code": r["project_code"], "project_name": r["project_name"]}).eq("id", int(r["id"])).execute()
            st.rerun()
        if c_del.button("🗑️ DELETE SELECTED PROJECTS", type="primary", use_container_width=True):
            ids_p = [int(i) for i in ed_p[ed_p["Select"] == True]["id"].tolist()]
            for i_p in ids_p: supabase.table("projects").delete().eq("id", i_p).execute()
            st.rerun()
    with t2:
        st.subheader("User Management")
        u_mail = st.text_input("Authorize Email")
        if st.button("Authorize"):
            supabase.table("user_permissions").insert({"email": u_mail.lower()}).execute(); st.rerun()
        
        users = supabase.table("user_permissions").select("*").execute().data
        if users:
            all_p = supabase.table("projects").select("id, project_code").execute().data
            p_opts = {f"{p['project_code']}": int(p['id']) for p in all_p}
            
            u_to_edit = st.selectbox("Assign Projects to User:", [u['email'] for u in users])
            selected_projects = st.multiselect("Select Projects:", list(p_opts.keys()))
            if st.button("💾 Update Permissions"):
                new_ids = [int(p_opts[p]) for p in selected_projects]
                # FIX: Inviare i dati come lista di interi standard Python
                supabase.table("user_permissions").update({"allowed_projects": new_ids}).eq("email", u_to_edit).execute()
                st.success("Permissions updated!")
            
            st.write("---")
            df_u = pd.DataFrame(users)
            df_u.insert(0, "Select", False)
            ed_u = st.data_editor(df_u, use_container_width=True, hide_index=True, column_config={"id": None})
            if st.button("🗑️ Delete Selected Users"):
                for _, r in ed_u[ed_u["Select"] == True].iterrows():
                    supabase.table("user_permissions").delete().eq("email", r["email"]).execute()
                st.rerun()
