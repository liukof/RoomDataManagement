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
allowed_ids = current_user.get("allowed_projects") or []

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

if not projects_list and not is_admin:
    st.warning("No projects assigned to your user.")
    st.stop()

# --- GLOBAL CONTEXT (Se esistono progetti) ---
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

    with st.expander("📥 Bulk Import / Export / Reset Rooms"):
        c1, c2, c3 = st.columns(3)
        with c1:
            st.write("**Export**")
            rooms_raw = supabase.table("rooms").select("*").eq("project_id", project_id).order("room_number").execute()
            if rooms_raw.data:
                df_exp = pd.DataFrame([{"Number": r["room_number"], "Name": r["room_name_planned"], **(r.get("parameters") or {})} for r in rooms_raw.data])
                buf = io.BytesIO()
                with pd.ExcelWriter(buf, engine='xlsxwriter') as writer: df_exp.to_excel(writer, index=False)
                st.download_button("⬇️ Download Excel", data=buf.getvalue(), file_name="rooms_export.xlsx")
        with c2:
            st.write("**Import**")
            up_file = st.file_uploader("Upload Rooms XLSX", type=["xlsx"], key="up_rooms")
            if up_file and st.button("🚀 Sync Rooms"):
                df_up = pd.read_excel(up_file, dtype=str)
                bulk_data = []
                for _, row in df_up.iterrows():
                    r_num = str(row.get("Number", "")).strip()
                    if r_num.endswith('.0'): r_num = r_num[:-2]
                    p_save = {p: row[p] for p in mapped_params if p in row and pd.notna(row[p])}
                    bulk_data.append({"project_id": project_id, "room_number": r_num, "room_name_planned": str(row.get("Name", "")), "parameters": p_save})
                supabase.table("rooms").upsert(bulk_data, on_conflict="project_id,room_number").execute()
                st.success("Rooms Updated!"); st.rerun()
        with c3:
            st.write("**Danger Zone**")
            if st.button("🗑️ DELETE ALL PROJECT ROOMS"):
                supabase.table("rooms").delete().eq("project_id", project_id).execute(); st.rerun()

    st.divider()
    cf1, cf2 = st.columns([2, 1])
    search_q = cf1.text_input("🔍 Search Room (Number or Name)", placeholder="e.g. degenza")
    group_by = cf2.selectbox("📂 Group By:", ["None"] + mapped_params)
    
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
        df_filtered = df[mask]

        st.write(f"### 📍 Filtered Rooms ({len(df_filtered)})")
        st.dataframe(df_filtered, use_container_width=True, hide_index=True, column_config={"id": None})

        # --- BULK ITEM ADD (dRofus Style) ---
        st.divider()
        st.subheader("📦 Bulk Equipment Assignment")
        catalog = supabase.table("items").select("*").eq("project_id", project_id).execute().data
        if catalog:
            item_opt = {f"{i['item_code']} - {i['item_description']}": int(i['id']) for i in catalog}
            with st.form("bulk_item_form"):
                col_i1, col_i2 = st.columns([3, 1])
                t_item_label = col_i1.selectbox("Select Item to add to ALL filtered rooms:", list(item_opt.keys()))
                t_qty = col_i2.number_input("Qty per Room", min_value=1, value=1)
                if st.form_submit_button("🚀 Add Item to All Filtered Rooms", use_container_width=True):
                    bulk_insert = [{"room_id": int(r_id), "item_id": item_opt[t_item_label], "quantity": int(t_qty)} for r_id in df_filtered['id'].tolist()]
                    if bulk_insert:
                        supabase.table("room_items").insert(bulk_insert).execute()
                        st.success(f"Added to {len(df_filtered)} rooms!"); st.rerun()

# --- 6. PAGE: ITEM CATALOG ---
elif menu == "📦 Item Catalog":
    if not project_id: st.stop()
    st.header("📦 Item Catalog Management")
    with st.form("new_item"):
        c1, c2 = st.columns(2)
        i_c = c1.text_input("Item Code")
        i_d = c2.text_input("Description")
        if st.form_submit_button("Save Item"):
            supabase.table("items").insert({"project_id": project_id, "item_code": i_c, "item_description": i_d}).execute(); st.rerun()

    items_data = supabase.table("items").select("*").eq("project_id", project_id).execute().data
    if items_data:
        df_items = pd.DataFrame(items_data).drop(columns=['project_id'])
        df_items["Delete"] = False
        ed_catalog = st.data_editor(df_items, use_container_width=True, hide_index=True, column_config={"id": None})
        if st.button("🗑️ Delete Selected Items"):
            for _, r in ed_catalog[ed_catalog["Delete"] == True].iterrows():
                supabase.table("items").delete().eq("id", int(r["id"])).execute()
            st.rerun()

# --- 7. PAGE: PARAMETER MAPPING ---
elif menu == "🔗 Parameter Mapping":
    if not project_id: st.stop()
    st.header("🔗 Parameter Mapping")
    with st.expander("📥 Bulk Import / Export Mappings"):
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
        c1, c2 = st.columns(2)
        db_p, rv_p = c1.text_input("DB Param"), c2.text_input("Revit Param")
        if st.form_submit_button("Add Single Mapping"):
            supabase.table("parameter_mappings").insert({"project_id": project_id, "db_column_name": db_p, "revit_parameter_name": rv_p}).execute(); st.rerun()
            
    maps = supabase.table("parameter_mappings").select("*").eq("project_id", project_id).execute().data
    if maps:
        df_m = pd.DataFrame(maps)[["id", "db_column_name", "revit_parameter_name"]]
        df_m["Delete"] = False
        ed_m = st.data_editor(df_m, use_container_width=True, hide_index=True, column_config={"id": None})
        if st.button("🗑️ Delete Selected Mappings"):
            for _, r in ed_m[ed_m["Delete"] == True].iterrows():
                supabase.table("parameter_mappings").delete().eq("id", int(r["id"])).execute(); st.rerun()

# --- 8. PAGE: SYSTEM MANAGEMENT ---
elif menu == "⚙️ System Management" and is_admin:
    st.header("⚙️ Admin Panel")
    t1, t2 = st.tabs(["🏗️ Projects", "👥 Users"])
    with t1:
        with st.form("new_p"):
            p_c, p_n = st.text_input("New Project Code"), st.text_input("New Project Name")
            if st.form_submit_button("Create Project"):
                supabase.table("projects").insert({"project_code": p_c, "project_name": p_n}).execute(); st.rerun()
        st.divider()
        st.write("**Delete Projects**")
        if projects_list:
            df_p = pd.DataFrame(projects_list)[["id", "project_code", "project_name"]]
            df_p["Delete"] = False
            ed_p = st.data_editor(df_p, use_container_width=True, hide_index=True, column_config={"id": None})
            if st.button("🗑️ DELETE SELECTED PROJECTS", type="primary"):
                for _, r in ed_p[ed_p["Delete"] == True].iterrows():
                    supabase.table("projects").delete().eq("id", int(r["id"])).execute()
                st.rerun()
    with t2:
        u_m = st.text_input("Authorize Email")
        if st.button("Add User"):
            supabase.table("user_permissions").insert({"email": u_m.lower(), "is_admin": False}).execute(); st.rerun()
        u_list = supabase.table("user_permissions").select("*").execute().data
        if u_list: st.dataframe(pd.DataFrame(u_list), use_container_width=True, hide_index=True)
