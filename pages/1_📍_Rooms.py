import streamlit as st
import pandas as pd
from supabase import create_client, Client
import io

# --- SETUP & AUTH ---
url, key = st.secrets["SUPABASE_URL"], st.secrets["SUPABASE_KEY"]
supabase: Client = create_client(url, key)

if "user_data" not in st.session_state or st.session_state["user_data"] is None:
    st.switch_page("app.py")
    st.stop()

current_user = st.session_state["user_data"]
is_admin = current_user.get("is_admin", False)
allowed_ids = [int(i) for i in (current_user.get("allowed_projects") or [])]

# --- PROJECT CONTEXT ---
st.sidebar.title("🏗️ BIM Manager")
query = supabase.table("projects").select("*").order("project_code")
if not is_admin:
    query = query.in_("id", allowed_ids if allowed_ids else [0])
projects_list = query.execute().data

if not projects_list:
    st.error("Nessun progetto assegnato.")
    st.stop()

project_options = {f"{p['project_code']} - {p['project_name']}": p for p in projects_list}
selected_label = st.selectbox("Current Project Context:", list(project_options.keys()))
project_id = int(project_options[selected_label]['id'])

st.header("📍 Rooms & Item Lists")

# --- PARAMETER MAPPING CONTEXT ---
maps_resp = supabase.table("parameter_mappings").select("db_column_name").eq("project_id", project_id).execute()
mapped_params = [m['db_column_name'] for m in maps_resp.data]

# --- SECTION: IMPORT / EXPORT ---
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
                    st.success(f"Room {new_r_num} added!")
                    st.rerun()
    
    with tab_bulk:
        c1, c2 = st.columns(2)
        with c1:
            st.write("**Export Rooms**")
            rooms_raw = supabase.table("rooms").select("*").eq("project_id", project_id).order("room_number").execute()
            if rooms_raw.data:
                # Inclusione dell'Area nell'Export Excel
                df_exp = pd.DataFrame([{"Number": r["room_number"], "Name": r["room_name_planned"], "Area (mq)": r.get("area", 0), **(r.get("parameters") or {})} for r in rooms_raw.data])
                buf = io.BytesIO()
                with pd.ExcelWriter(buf, engine='xlsxwriter') as writer:
                    df_exp.to_excel(writer, index=False)
                st.download_button("⬇️ Download Excel", data=buf.getvalue(), file_name="rooms_export.xlsx")
        with c2:
            st.write("**Import Rooms**")
            up_file = st.file_uploader("Upload XLSX", type=["xlsx"])
            if up_file and st.button("🚀 Sync Rooms"):
                df_up = pd.read_excel(up_file, dtype=str)
                bulk_data = []
                for _, row in df_up.iterrows():
                    params = {p: row[p] for p in mapped_params if p in row and pd.notna(row[p])}
                    bulk_data.append({
                        "project_id": project_id, 
                        "room_number": str(row["Number"]).strip(), 
                        "room_name_planned": str(row["Name"]), 
                        "parameters": params
                    })
                supabase.table("rooms").upsert(bulk_data, on_conflict="project_id,room_number").execute()
                st.success("Bulk sync complete!")
                st.rerun()

# --- SECTION: ROOMS TABLE ---
st.divider()
search_q = st.text_input("🔍 Filter (Number or Name)", placeholder="e.g. degenza")
rooms_resp = supabase.table("rooms").select("*").eq("project_id", project_id).order("room_number").execute()

if rooms_resp.data:
    flat_data = []
    for r in rooms_resp.data:
        # Recupero colonna piatta 'area'
        row = {
            "id": int(r["id"]), 
            "Number": r["room_number"], 
            "Name": r["room_name_planned"],
            "Area (mq)": float(r.get("area") or 0)
        }
        p_json = r.get("parameters") or {}
        for p in mapped_params:
            row[p] = p_json.get(p, "")
        flat_data.append(row)
    
    df = pd.DataFrame(flat_data)
    
    mask = df.apply(lambda x: x.astype(str).str.contains(search_q, case=False).any(), axis=1) if search_q else [True]*len(df)
    df_filtered = df[mask].copy()
    df_filtered.insert(0, "Select", False)

    st.write(f"### 📍 Rooms List ({len(df_filtered)})")
    
    # Configurazione colonne: l'Area è in sola lettura (Read-Only)
    ed_rooms = st.data_editor(
        df_filtered, 
        use_container_width=True, 
        hide_index=True, 
        column_config={
            "id": None, 
            "Area (mq)": st.column_config.NumberColumn(
                label="📐 Area (mq)",
                format="%.2f m²", 
                help="Dato da Revit", 
                disabled=True
            )
        }
    )
    
    col_del1, col_del2 = st.columns(2)
    if col_del1.button("🗑️ DELETE SELECTED", use_container_width=True):
        ids = [int(i) for i in ed_rooms[ed_rooms["Select"] == True]["id"].tolist()]
        if ids:
            supabase.table("rooms").delete().in_("id", ids).execute()
            st.rerun()
    if col_del2.button("⚠️ DELETE ALL PROJECT ROOMS", type="primary", use_container_width=True):
        supabase.table("rooms").delete().eq("project_id", project_id).execute()
        st.rerun()

    # --- BULK ITEM ASSIGNMENT ---
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
                supabase.table("room_items").insert(bulk).execute()
                st.success(f"Added to {len(bulk)} rooms!")
                st.rerun()
