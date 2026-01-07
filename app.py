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
    if not project_id: st.info("Create a project first."); st.stop()
    
    maps_resp = supabase.table("parameter_mappings").select("db_column_name").eq("project_id", project_id).execute()
    mapped_params = [m['db_column_name'] for m in maps_resp.data]

    # SEZIONE IMPORT / EXPORT / ADD SINGLE
    with st.expander("📥 Manage Rooms (Import / Export / Manual Add)"):
        tab_manual, tab_bulk = st.tabs(["➕ Add Single Room", "📁 Bulk Excel Sync"])
        
        with tab_manual:
            with st.form("single_room_form"):
                c1, c2 = st.columns(2)
                new_r_num = c1.text_input("Room Number")
                new_r_name = c2.text_input("Room Name")
                if st.form_submit_button("➕ Create Single Room"):
                    if new_r_num and new_r_name:
                        supabase.table("rooms").insert({"project_id": project_id, "room_number": new_r_num, "room_name_planned": new_r_name}).execute()
                        st.success(f"Room {new_r_num} added!"); st.rerun()
        
        with tab_bulk:
            c1, c2 = st.columns(2)
            with c1:
                rooms_raw = supabase.table("rooms").select("*").eq("project_id", project_id).order("room_number").execute()
                if rooms_raw.data:
                    df_exp = pd.DataFrame([{"Number": r["room_number"], "Name": r["room_name_planned"], **(r.get("parameters") or {})} for r in rooms_raw.data])
                    buf = io.BytesIO()
                    with pd.ExcelWriter(buf, engine='xlsxwriter') as writer: df_exp.to_excel(writer, index=False)
                    st.download_button("⬇️ Download Excel", data=buf.getvalue(), file_name="rooms_export.xlsx")
            with c2:
                up_file = st.file_uploader("Upload XLSX", type=["xlsx"])
                if up_file and st.button("🚀 Sync Rooms"):
                    df_up = pd.read_excel(up_file, dtype=str)
                    bulk_data = [{"project_id": project_id, "room_number": str(row["Number"]).strip(), "room_name_planned": str(row["Name"]), "parameters": {p: row[p] for p in mapped_params if p in row and pd.notna(row[p])}} for _, row in df_up.iterrows()]
                    supabase.table("rooms").upsert(bulk_data, on_conflict="project_id,room_number").execute()
                    st.success("Bulk sync complete!"); st.rerun()

    st.divider()
    search_q = st.text_input("🔍 Filter (Number or Name)", placeholder="e.g. degenza")
    
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
            ids = [int(i) for i in ed_rooms[ed_rooms["Select"] == True]["id"].tolist()]
            if ids: supabase.table("rooms").delete().in_("id", ids).execute(); st.rerun()
        if col_del2.button("⚠️ DELETE ALL PROJECT ROOMS", type="primary", use_container_width=True):
            supabase.table("rooms").delete().eq("project_id", project_id).execute(); st.rerun()

        # BULK ADD ITEM
        st.divider()
        st.subheader("📦 Bulk Item Assignment")
        catalog = supabase.table("items").select("*").eq("project_id", project_id).execute().data
        if catalog:
            item_opt = {f"{i['item_code']} - {i['item_description']}": int(i['id']) for i in catalog}
            with st.form("bulk_item"):
                c1, c2 = st.columns([3, 1])
                t_item = c1.selectbox("Add Item to ALL filtered rooms:", list(item_opt.keys()))
                t_qty = c2.number_input("Qty", min_value=1, value=1)
                if st.form_submit_button("🚀 Add to Filtered Set"):
                    bulk = [{"room_id": int(rid), "item_id": item_opt[t_item], "quantity": int(t_qty)} for rid in df_filtered['id'].tolist()]
                    supabase.table("room_items").insert(bulk).execute(); st.rerun()

# --- 6. PAGE: ITEM CATALOG ---
elif menu == "📦 Item Catalog":
    if not project_id: st.stop()
    st.header("📦 Item Catalog Management")
    with st.expander("➕ Add New Item"):
        with st.form("ni"):
            c1, c2 = st.columns(2)
            ic, ides = c1.text_input("Code"), c2.text_input("Description")
            if st.form_submit_button("Save Item"):
                if ic: supabase.table("items").insert({"project_id": project_id, "item_code": ic, "item_description": ides}).execute(); st.rerun()

    st.write("---")
    si = st.text_input("🔍 Filter Items")
    items = supabase.table("items").select("*").eq("project_id", project_id).execute().data
    if items:
        df_i = pd.DataFrame(items).drop(columns=['project_id'])
        if si: df_i = df_i[df_i.apply(lambda x: x.astype(str).str.contains(si, case=False).any(), axis=1)]
        df_i.insert(0, "Select", False)
        ed_i = st.data_editor(df_i, use_container_width=True, hide_index=True, column_config={"id": None})
        if st.button("🗑️ Delete Selected Items"):
            ids = [int(i) for i in ed_i[ed_i["Select"] == True]["id"].tolist()]
            if ids: supabase.table("items").delete().in_("id", ids).execute(); st.rerun()

# --- 7. PAGE: PARAMETER MAPPING ---
elif menu == "🔗 Parameter Mapping":
    if not project_id: st.stop()
    st.header("🔗 Parameter Mapping")
    with st.expander("📥 Import / Export Mappings"):
        c1, c2 = st.columns(2)
        with c1:
            maps = supabase.table("parameter_mappings").select("*").eq("project_id", project_id).execute().data
            if maps:
                df_m_exp = pd.DataFrame(maps)[["db_column_name", "revit_parameter_name"]]
                buf = io.BytesIO()
                with pd.ExcelWriter(buf, engine='xlsxwriter') as writer: df_m_exp.to_excel(writer, index=False)
                st.download_button("⬇️ Download Excel", data=buf.getvalue(), file_name="mappings.xlsx")
        with c2:
            up_m = st.file_uploader("Upload Mappings", type=["xlsx"])
            if up_m and st.button("🚀 Upload"):
                df_m_up = pd.read_excel(up_m, dtype=str)
                m_bulk = [{"project_id": project_id, "db_column_name": str(row["db_column_name"]), "revit_parameter_name": str(row["revit_parameter_name"])} for _, row in df_m_up.iterrows()]
                supabase.table("parameter_mappings").upsert(m_bulk, on_conflict="project_id,db_column_name").execute(); st.rerun()

    with st.form("new_m"):
        c1, c2 = st.columns(2)
        dbp, rvp = c1.text_input("DB Param"), c2.text_input("Revit Param")
        if st.form_submit_button("Add Mapping"):
            if dbp and rvp: supabase.table("parameter_mappings").insert({"project_id": project_id, "db_column_name": dbp, "revit_parameter_name": rvp}).execute(); st.rerun()

    maps_data = supabase.table("parameter_mappings").select("*").eq("project_id", project_id).execute().data
    if maps_data:
        df_m = pd.DataFrame(maps_data)[["id", "db_column_name", "revit_parameter_name"]]
        df_m.insert(0, "Select", False)
        ed_m = st.data_editor(df_m, use_container_width=True, hide_index=True, column_config={"id": None})
        if st.button("🗑️ Delete Selected Mappings"):
            ids = [int(i) for i in ed_m[ed_m["Select"] == True]["id"].tolist()]
            if ids: supabase.table("parameter_mappings").delete().in_("id", ids).execute(); st.rerun()

# --- 8. PAGE: SYSTEM MANAGEMENT ---
elif menu == "⚙️ System Management" and is_admin:
    st.header("⚙️ Admin Panel")
    t1, t2 = st.tabs(["🏗️ Projects", "👥 Users"])
    with t1:
        with st.form("np"):
            pc, pn = st.text_input("Project Code"), st.text_input("Project Name")
            if st.form_submit_button("Create Project"):
                supabase.table("projects").insert({"project_code": pc, "project_name": pn}).execute(); st.rerun()
        st.divider()
        pall = supabase.table("projects").select("*").execute().data
        if pall:
            dfp = pd.DataFrame(pall)[["id", "project_code", "project_name"]]
            dfp.insert(0, "Select", False)
            edp = st.data_editor(dfp, use_container_width=True, hide_index=True, column_config={"id": None})
            cs, cd = st.columns(2)
            if cs.button("💾 SAVE CHANGES (RENAME)", use_container_width=True):
                for _, r in edp.iterrows():
                    supabase.table("projects").update({"project_code": r["project_code"], "project_name": r["project_name"]}).eq("id", int(r["id"])).execute()
                st.rerun()
            if cd.button("🗑️ DELETE SELECTED PROJECTS", type="primary", use_container_width=True):
                for _, r in edp[edp["Select"] == True].iterrows():
                    supabase.table("projects").delete().eq("id", int(r["id"])).execute()
                st.rerun()
    with t2:
        st.subheader("User Management")
        um = st.text_input("Authorize Email")
        if st.button("Authorize"):
            supabase.table("user_permissions").insert({"email": um.lower()}).execute(); st.rerun()
        
        users = supabase.table("user_permissions").select("*").execute().data
        if users:
            projs = supabase.table("projects").select("id, project_code").execute().data
            p_map = {p['project_code']: int(p['id']) for p in projs}
            u_to_ed = st.selectbox("Assign Projects to User:", [u['email'] for u in users])
            curr_u = next(u for u in users if u['email'] == u_to_ed)
            curr_ids = [int(x) for x in (curr_u.get("allowed_projects") or [])]
            curr_labels = [k for k, v in p_map.items() if v in curr_ids]
            sel_p = st.multiselect("Select Projects:", list(p_map.keys()), default=curr_labels)
            if st.button("💾 Update Permissions"):
                new_ids = [int(p_map[p]) for p in sel_p]
                supabase.table("user_permissions").update({"allowed_projects": new_ids}).eq("email", u_to_ed).execute(); st.rerun()
            st.divider()
            df_u = pd.DataFrame(users)
            df_u.insert(0, "Select", False)
            ed_u = st.data_editor(df_u, use_container_width=True, hide_index=True, column_config={"id": None})
            if st.button("🗑️ Delete Selected Users"):
                for _, r in ed_u[ed_u["Select"] == True].iterrows():
                    supabase.table("user_permissions").delete().eq("email", r["email"]).execute()
                st.rerun()
