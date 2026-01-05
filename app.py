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
    query = query.in_("id", allowed_ids if allowed_ids else ['00000000-0000-0000-0000-000000000000'])
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

# Project context selector (Global)
project_options = {f"{p['project_code']} - {p['project_name']}": p for p in projects_list}
selected_label = st.selectbox("Current Project Context:", list(project_options.keys()))
project_id = project_options[selected_label]['id']

# --- 5. PAGE: ROOMS & ITEM LISTS ---
if menu == "📍 Rooms & Item Lists":
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
                with pd.ExcelWriter(buf, engine='xlsxwriter') as writer:
                    df_exp.to_excel(writer, index=False)
                st.download_button("⬇️ Download Rooms Excel", data=buf.getvalue(), file_name="rooms_export.xlsx")
        
        with c2:
            st.write("**Import (Bulk Sync)**")
            up_file = st.file_uploader("Upload Rooms XLSX", type=["xlsx"])
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

    # Filtri dRofus Style
    st.divider()
    cf1, cf2 = st.columns([2, 1])
    search_q = cf1.text_input("🔍 Search Room Number/Name")
    group_by = cf2.selectbox("📂 Group By:", ["None"] + mapped_params)
    
    rooms_resp = supabase.table("rooms").select("*").eq("project_id", project_id).order("room_number").execute()
    if rooms_resp.data:
        flat_data = []
        for r in rooms_resp.data:
            row = {"id": r["id"], "Number": r["room_number"], "Name": r["room_name_planned"], **(r.get("parameters") or {})}
            flat_data.append(row)
        df = pd.DataFrame(flat_data)
        
        if search_q:
            df = df[df['Number'].str.contains(search_q, case=False) | df['Name'].str.contains(search_q, case=False)]

        if group_by != "None":
            for g_name, g_df in df.groupby(group_by):
                with st.expander(f"📁 {group_by}: {g_name} ({len(g_df)} rooms)"):
                    st.dataframe(g_df, use_container_width=True, hide_index=True)
        else:
            sel_num = st.selectbox("Select Room to manage Items:", df['Number'].tolist())
            room_id = df[df['Number'] == sel_num]['id'].values[0]
            
            # --- ITEM LIST LOGIC ---
            st.subheader(f"📦 Item List: Room {sel_num}")
            items_in_room = supabase.table("room_items").select("id, quantity, items(item_code, item_description)").eq("room_id", room_id).execute()
            if items_in_room.data:
                item_rows = [{"Code": ri["items"]["item_code"], "Description": ri["items"]["item_description"], "Qty": ri["quantity"], "id": ri["id"]} for ri in items_in_room.data]
                ed_items = st.data_editor(pd.DataFrame(item_rows), use_container_width=True, hide_index=True, column_config={"id": None})
                if st.button("🗑️ Delete Selected Items"):
                    # Logica per eliminare...
                    pass
            
            catalog = supabase.table("items").select("*").eq("project_id", project_id).execute().data
            if catalog:
                item_opt = {f"{i['item_code']} - {i['item_description']}": i['id'] for i in catalog}
                ci1, ci2 = st.columns([3, 1])
                t_item = ci1.selectbox("Add Item:", list(item_opt.keys()))
                t_qty = ci2.number_input("Qty", min_value=1, value=1)
                if st.button("➕ Add Item"):
                    supabase.table("room_items").insert({"room_id": room_id, "item_id": item_opt[t_item], "quantity": t_qty}).execute()
                    st.rerun()

# --- 6. PAGE: ITEM CATALOG ---
elif menu == "📦 Item Catalog":
    st.header("📦 Item Catalog Management")
    c1, c2 = st.columns(2)
    with c1:
        with st.expander("➕ Add Single Item"):
            with st.form("new_item"):
                i_c = st.text_input("Item Code")
                i_d = st.text_input("Description")
                if st.form_submit_button("Save"):
                    supabase.table("items").insert({"project_id": project_id, "item_code": i_c, "item_description": i_d}).execute()
                    st.rerun()
    with c2:
        st.write("**Bulk Actions**")
        if st.button("🗑️ Clear Catalog"):
            supabase.table("items").delete().eq("project_id", project_id).execute()
            st.rerun()

    items_data = supabase.table("items").select("*").eq("project_id", project_id).execute().data
    if items_data:
        st.data_editor(pd.DataFrame(items_data).drop(columns=['project_id']), use_container_width=True, hide_index=True)

# --- 7. PAGE: PARAMETER MAPPING ---
elif menu == "🔗 Parameter Mapping":
    st.header("🔗 Parameter Mapping")
    c1, c2 = st.columns(2)
    with c1:
        with st.form("map_f"):
            db_p = st.text_input("DB Param")
            rv_p = st.text_input("Revit Param")
            if st.form_submit_button("Add"):
                supabase.table("parameter_mappings").insert({"project_id": project_id, "db_column_name": db_p, "revit_parameter_name": rv_p}).execute()
                st.rerun()
    with c2:
        if st.button("🗑️ Clear Mappings"):
            supabase.table("parameter_mappings").delete().eq("project_id", project_id).execute()
            st.rerun()
            
    maps = supabase.table("parameter_mappings").select("*").eq("project_id", project_id).execute().data
    if maps:
        st.table(pd.DataFrame(maps)[["db_column_name", "revit_parameter_name"]])

# --- 8. PAGE: SYSTEM MANAGEMENT ---
elif menu == "⚙️ System Management" and is_admin:
    st.header("⚙️ Admin")
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
