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

if not projects_list:
    st.warning("No projects available.")
    st.stop()

project_options = {f"{p['project_code']} - {p['project_name']}": p for p in projects_list}
selected_label = st.selectbox("Current Project Context:", list(project_options.keys()))
project_id = int(project_options[selected_label]['id'])

# --- 5. PAGE: ROOMS & ITEM LISTS ---
if menu == "📍 Rooms & Item Lists":
    maps_resp = supabase.table("parameter_mappings").select("db_column_name").eq("project_id", project_id).execute()
    mapped_params = [m['db_column_name'] for m in maps_resp.data]

    with st.expander("📥 Bulk Import / Export / Reset Rooms"):
        c1, c2, c3 = st.columns(3)
        with c1:
            st.write("**Export Rooms**")
            rooms_raw = supabase.table("rooms").select("*").eq("project_id", project_id).order("room_number").execute()
            if rooms_raw.data:
                df_exp = pd.DataFrame([{"Number": r["room_number"], "Name": r["room_name_planned"], **(r.get("parameters") or {})} for r in rooms_raw.data])
                buf = io.BytesIO()
                with pd.ExcelWriter(buf, engine='xlsxwriter') as writer:
                    df_exp.to_excel(writer, index=False)
                st.download_button("⬇️ Download Excel", data=buf.getvalue(), file_name="rooms_export.xlsx")
        with c2:
            st.write("**Import Rooms (Bulk Sync)**")
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
                st.success("Rooms Updated!")
                st.rerun()
        with c3:
            st.write("**Danger Zone**")
            if st.button("🗑️ DELETE ALL PROJECT ROOMS"):
                supabase.table("rooms").delete().eq("project_id", project_id).execute()
                st.rerun()

    st.divider()
    cf1, cf2 = st.columns([2, 1])
    search_q = cf1.text_input("🔍 Filter Rooms (Number, Name, or Params)", placeholder="e.g. degenza")
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
        
        if search_q:
            mask = df.apply(lambda x: x.astype(str).str.contains(search_q, case=False).any(), axis=1)
            df_filtered = df[mask]
        else:
            df_filtered = df

        st.write(f"### 📍 Filtered Rooms List ({len(df_filtered)} rooms)")
        st.dataframe(df_filtered, use_container_width=True, hide_index=True, column_config={"id": None})

        # --- SEZIONE BULK ITEM ADD (dRofus Style) ---
        st.divider()
        st.subheader("📦 Bulk Equipment Assignment")
        st.warning(f"Warning: Actions below will apply to ALL {len(df_filtered)} filtered rooms.")
        
        catalog = supabase.table("items").select("*").eq("project_id", project_id).execute().data
        if catalog:
            item_opt = {f"{i['item_code']} - {i['item_description']}": int(i['id']) for i in catalog}
            
            with st.form("bulk_item_form"):
                col_i1, col_i2 = st.columns([3, 1])
                t_item_label = col_i1.selectbox("Select Item to add to filtered set:", list(item_opt.keys()))
                t_qty = col_i2.number_input("Quantity per Room", min_value=1, value=1)
                
                if st.form_submit_button("🚀 Add to All Filtered Rooms", use_container_width=True):
                    bulk_insert = []
                    item_id = item_opt[t_item_label]
                    for r_id in df_filtered['id'].tolist():
                        bulk_insert.append({"room_id": int(r_id), "item_id": item_id, "quantity": int(t_qty)})
                    if bulk_insert:
                        supabase.table("room_items").insert(bulk_insert).execute()
                        st.success(f"Successfully added to {len(df_filtered)} rooms!")
                        st.rerun()

# --- 6. PAGE: ITEM CATALOG ---
elif menu == "📦 Item Catalog":
    st.header("📦 Item Catalog Management")
    with st.expander("➕ Add Single Item"):
        with st.form("new_item"):
            i_c = st.text_input("Item Code")
            i_d = st.text_input("Description")
            if st.form_submit_button("Save Item"):
                supabase.table("items").insert({"project_id": project_id, "item_code": i_c, "item_description": i_d}).execute()
                st.rerun()

    items_data = supabase.table("items").select("*").eq("project_id", project_id).execute().data
    if items_data:
        df_items = pd.DataFrame(items_data).drop(columns=['project_id'])
        df_items["Delete"] = False
        ed_catalog = st.data_editor(df_items, use_container_width=True, hide_index=True, key="cat_ed", column_config={"id": None})
        if st.button("🗑️ Delete Selected from Catalog"):
            for _, r in ed_catalog[ed_catalog["Delete"] == True].iterrows():
                supabase.table("items").delete().eq("id", int(r["id"])).execute()
            st.rerun()

# --- 7. PAGE: PARAMETER MAPPING (RIPRISTINATO IMPORT/EXPORT) ---
elif menu == "🔗 Parameter Mapping":
    st.header("🔗 Parameter Mapping")
    
    with st.expander("📥 Bulk Import / Export / Reset Mappings"):
        c1, c2, c3 = st.columns(3)
        with c1:
            st.write("**Export Mappings**")
            maps_raw = supabase.table("parameter_mappings").select("*").eq("project_id", project_id).execute().data
            if maps_raw:
                df_maps_exp = pd.DataFrame(maps_raw)[["db_column_name", "revit_parameter_name"]]
                buf_m = io.BytesIO()
                with pd.ExcelWriter(buf_m, engine='xlsxwriter') as writer:
                    df_maps_exp.to_excel(writer, index=False)
                st.download_button("⬇️ Download Mapping Excel", data=buf_m.getvalue(), file_name="mappings_export.xlsx")
        with c2:
            st.write("**Import Mappings (Bulk)**")
            up_maps = st.file_uploader("Upload Mapping XLSX", type=["xlsx"], key="up_maps")
            if up_maps and st.button("🚀 Upload Mappings"):
                df_m_up = pd.read_excel(up_maps, dtype=str)
                m_bulk = []
                for _, row in df_m_up.iterrows():
                    db_col = str(row.get("db_column_name", "")).strip()
                    rv_param = str(row.get("revit_parameter_name", "")).strip()
                    if db_col and rv_param:
                        m_bulk.append({"project_id": project_id, "db_column_name": db_col, "revit_parameter_name": rv_param})
                if m_bulk:
                    supabase.table("parameter_mappings").upsert(m_bulk, on_conflict="project_id,db_column_name").execute()
                    st.success("Mappings Updated!")
                    st.rerun()
        with c3:
            st.write("**Danger Zone**")
            if st.button("🗑️ RESET ALL MAPPINGS"):
                supabase.table("parameter_mappings").delete().eq("project_id", project_id).execute()
                st.rerun()

    with st.form("map_f"):
        c1, c2 = st.columns(2)
        db_p = c1.text_input("New DB Param")
        rv_p = c2.text_input("New Revit Param")
        if st.form_submit_button("Add Single Mapping"):
            supabase.table("parameter_mappings").insert({"project_id": project_id, "db_column_name": db_p, "revit_parameter_name": rv_p}).execute()
            st.rerun()
            
    maps = supabase.table("parameter_mappings").select("*").eq("project_id", project_id).execute().data
    if maps:
        df_maps = pd.DataFrame(maps)[["id", "db_column_name", "revit_parameter_name"]]
        df_maps["Delete"] = False
        ed_maps = st.data_editor(df_maps, use_container_width=True, hide_index=True, key="map_ed", column_config={"id": None})
        if st.button("🗑️ Delete Selected Mappings"):
            for _, r in ed_maps[ed_maps["Delete"] == True].iterrows():
                supabase.table("parameter_mappings").delete().eq("id", int(r["id"])).execute()
            st.rerun()

# --- 8. PAGE: SYSTEM MANAGEMENT ---
elif menu == "⚙️ System Management" and is_admin:
    st.header("⚙️ Admin Panel")
    t1, t2 = st.tabs(["🏗️ Projects", "👥 Users"])
    with t1:
        with st.form("p_f"):
            p_c = st.text_input("Code")
            p_n = st.text_input("Name")
            if st.form_submit_button("Create"):
                supabase.table("projects").insert({"project_code": p_c, "project_name": p_n}).execute()
                st.rerun()
    with t2:
        u_m = st.text_input("User Email")
        if st.button("Authorize"):
            supabase.table("user_permissions").insert({"email": u_m.lower(), "is_admin": False}).execute()
            st.rerun()
