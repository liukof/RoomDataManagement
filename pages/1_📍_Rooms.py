import streamlit as st
import pandas as pd
from supabase import create_client, Client
import io

# --- 1. SETUP & CONNESSIONE ---
try:
    url = st.secrets["SUPABASE_URL"]
    key = st.secrets["SUPABASE_KEY"]
except KeyError:
    st.error("Configurazione mancante nei Secrets!")
    st.stop()

@st.cache_resource(ttl=3600)
def get_supabase_client() -> Client:
    return create_client(url, key)

supabase = get_supabase_client()

# --- 2. CONTROLLO ACCESSO ---
if "user_data" not in st.session_state or st.session_state["user_data"] is None:
    st.switch_page("app.py")
    st.stop()

current_user = st.session_state["user_data"]
is_admin = current_user.get("is_admin", False)
allowed_ids = [int(i) for i in (current_user.get("allowed_projects") or [])]

# --- 3. SIDEBAR & CONTESTO PROGETTO ---
st.sidebar.title("🏗️ BIM Manager")
st.sidebar.write(f"👤 **{current_user['email']}**")
if st.sidebar.button("🚪 Logout"):
    st.session_state["user_data"] = None
    st.switch_page("app.py")

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

# --- 4. MAPPING PARAMETRI ---
maps_resp = supabase.table("parameter_mappings").select("db_column_name").eq("project_id", project_id).execute()
mapped_params = [m['db_column_name'] for m in maps_resp.data]

# --- 5. SEZIONE IMPORT / EXPORT ---
with st.expander("📥 Manage Rooms (Import / Export / Manual Add)"):
    tab_manual, tab_bulk = st.tabs(["➕ Add Single Room", "📁 Bulk Excel Sync"])
    
    with tab_manual:
        with st.form("single_room_form"):
            c1, c2 = st.columns(2)
            new_r_num = c1.text_input("Room Number")
            new_r_name = c2.text_input("Room Name")
            if st.form_submit_button("➕ Create Single Room"):
                if new_r_num and new_r_name:
                    supabase.table("rooms").insert({
                        "project_id": project_id, 
                        "room_number": new_r_num.strip(), 
                        "room_name_planned": new_r_name.strip(),
                        "is_synced": False 
                    }).execute()
                    st.success(f"Room {new_r_num} added!"); st.rerun()
    
    with tab_bulk:
        c1, c2 = st.columns(2)
        with c1:
            st.write("**Export Rooms**")
            rooms_raw = supabase.table("rooms").select("*").eq("project_id", project_id).order("room_number").execute()
            if rooms_raw.data:
                df_exp = pd.DataFrame([
                    {
                        "Number": r["room_number"], 
                        "Name": r["room_name_planned"], 
                        "Area (mq)": r.get("area", 0),
                        **(r.get("parameters") or {})
                    } for r in rooms_raw.data
                ])
                buf = io.BytesIO()
                with pd.ExcelWriter(buf, engine='xlsxwriter') as writer: df_exp.to_excel(writer, index=False)
                st.download_button("⬇️ Download Excel", data=buf.getvalue(), file_name=f"rooms_{project_id}.xlsx", use_container_width=True)
        
        with c2:
            st.write("**Import Rooms**")
            up_file = st.file_uploader("Upload XLSX", type=["xlsx"], key="rooms_up")
            if up_file and st.button("🚀 Sync Rooms", use_container_width=True):
                df_up = pd.read_excel(up_file, dtype=str)
                bulk_data = []
                for _, row in df_up.iterrows():
                    params = {p: row[p] for p in mapped_params if p in row and pd.notna(row[p])}
                    bulk_data.append({
                        "project_id": project_id, 
                        "room_number": str(row["Number"]).strip(), 
                        "room_name_planned": str(row["Name"]), 
                        "parameters": params,
                        "is_synced": False 
                    })
                supabase.table("rooms").upsert(bulk_data, on_conflict="project_id,room_number").execute()
                st.success("Sincronizzazione completata!"); st.rerun()

# --- 6. TABELLA EDITABILE CON LOGICA 3 STATI ---
st.divider()
st.subheader("📑 Project Rooms")
c_info1, c_info2, c_info3 = st.columns(3)
c_info1.caption("✅ Sincronizzato")
c_info2.caption("⚠️ Modificato (Attesa Sync)")
c_info3.caption("❌ Mai Sincronizzato")

search_q = st.text_input("🔍 Filter Rooms", placeholder="Cerca numero o nome...")
rooms_resp = supabase.table("rooms").select("*").eq("project_id", project_id).order("room_number").execute()

if rooms_resp.data:
    flat_data = []
    for r in rooms_resp.data:
        sync_at = r.get("last_sync_at")
        is_synced = r.get("is_synced", False)
        
        # --- LOGICA ICONE 3 STATI ---
        if is_synced:
            status_icon = "✅"
        elif not is_synced and sync_at:
            status_icon = "⚠️"
        else:
            status_icon = "❌"
            
        sync_str = pd.to_datetime(sync_at).strftime('%d/%m/%Y %H:%M') if sync_at else "Mai"
        
        row = {
            "id": int(r["id"]), 
            "Status": status_icon,
            "Last Sync": sync_str,
            "Number": r["room_number"], 
            "Name": r["room_name_planned"], 
            "Area (mq)": float(r.get("area") or 0)
        }
        p_json = r.get("parameters") or {}
        for p in mapped_params: row[p] = p_json.get(p, "")
        flat_data.append(row)
    
    df_base = pd.DataFrame(flat_data)
    if search_q:
        mask = df_base.apply(lambda x: x.astype(str).str.contains(search_q, case=False).any(), axis=1)
        df_display = df_base[mask].copy()
    else:
        df_display = df_base.copy()
    
    df_display.insert(0, "Select", False)

    updated_df = st.data_editor(
        df_display,
        use_container_width=True,
        hide_index=True,
        column_config={
            "id": None, 
            "Status": st.column_config.TextColumn("Sync", width="small", help="✅ OK | ⚠️ Da aggiornare | ❌ Nuovo"),
            "Last Sync": st.column_config.TextColumn("Data Sync", width="medium"),
            "Number": st.column_config.TextColumn("Room Number", disabled=True),
            "Area (mq)": st.column_config.NumberColumn("📐 Area (mq)", format="%.2f m²", disabled=True),
            "Select": st.column_config.CheckboxColumn("Select", default=False)
        },
        key="rooms_editor_v3"
    )

    col_save, col_del_sel, col_del_all = st.columns([2, 1, 1])

    with col_save:
        if st.button("💾 SAVE ALL CHANGES", type="primary", use_container_width=True):
            success_count = 0
            for i in range(len(updated_df)):
                row_new = updated_df.iloc[i]
                row_old = df_display.iloc[i]
                new_params = {p: row_new[p] for p in mapped_params}
                old_params = {p: row_old[p] for p in mapped_params}
                
                if (row_new["Name"] != row_old["Name"]) or (new_params != old_params):
                    # AGGIORNAMENTO: Impostiamo is_synced a False. 
                    # Se last_sync_at esiste già, l'icona diventerà automaticamente ⚠️
                    supabase.table("rooms").update({
                        "room_name_planned": row_new["Name"],
                        "parameters": new_params,
                        "is_synced": False 
                    }).eq("id", int(row_new["id"])).execute()
                    success_count += 1
            
            if success_count > 0:
                st.success(f"Aggiornati {success_count} locali."); st.rerun()

    with col_del_sel:
        if st.button("🗑️ DELETE SELECTED", use_container_width=True):
            ids = updated_df[updated_df["Select"] == True]["id"].tolist()
            if ids:
                supabase.table("rooms").delete().in_("id", ids).execute()
                st.rerun()
    
    with col_del_all:
        if st.button("⚠️ DELETE ALL", type="secondary", use_container_width=True):
            supabase.table("rooms").delete().eq("project_id", project_id).execute()
            st.rerun()

# --- 7. ASSEGNAZIONE MASSIVA ITEM ---
st.divider()
st.subheader("📦 Bulk Item Assignment")
catalog = supabase.table("items").select("*").eq("project_id", project_id).execute().data
if catalog:
    item_opt = {f"{i['item_code']} - {i['item_description']}": int(i['id']) for i in catalog}
    with st.form("bulk_item"):
        c1, c2 = st.columns([3, 1])
        t_item = c1.selectbox("Seleziona Item:", list(item_opt.keys()))
        t_qty = c2.number_input("Quantità", min_value=1, value=1)
        if st.form_submit_button("🚀 Assign to Filtered Set", use_container_width=True):
            bulk = [{"room_id": int(rid), "item_id": item_opt[t_item], "quantity": int(t_qty)} for rid in df_display['id'].tolist()]
            supabase.table("room_items").insert(bulk).execute()
            st.success("Assegnazione completata!"); st.rerun()
