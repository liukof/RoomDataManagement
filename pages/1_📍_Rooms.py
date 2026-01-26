import streamlit as st
import pandas as pd
from supabase import create_client, Client
import io

# --- 1. SETUP & CONNESSIONE ---
try:
    url = st.secrets["SUPABASE_URL"]
    key = st.secrets["SUPABASE_KEY"]
except KeyError:
    st.error("Configurazione mancante nei Secrets! (SUPABASE_URL, SUPABASE_KEY)")
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

# --- 3. SIDEBAR & RECUPERO PROJECT_ID (Risolve il NameError) ---
st.sidebar.title("🏗️ BIM Manager")
st.sidebar.write(f"👤 **{current_user['email']}**")
if st.sidebar.button("🚪 Logout"):
    st.session_state["user_data"] = None
    st.switch_page("app.py")

# Caricamento progetti autorizzati per definire il contesto
proj_query = supabase.table("projects").select("*").order("project_code")
if not is_admin:
    proj_query = proj_query.in_("id", allowed_ids if allowed_ids else [0])
projects_list = proj_query.execute().data

if not projects_list:
    st.error("Nessun progetto assegnato al tuo profilo.")
    st.stop()

# Definizione del project_id tramite selectbox
project_options = {f"{p['project_code']} - {p['project_name']}": p['id'] for p in projects_list}
selected_proj_label = st.sidebar.selectbox("Project Context:", list(project_options.keys()))
project_id = project_options[selected_proj_label] # <--- Ora project_id è definito!

st.header("📍 Rooms & Sync Control")

# --- 4. MAPPING PARAMETRI ---
maps_resp = supabase.table("parameter_mappings").select("db_column_name").eq("project_id", project_id).execute()
mapped_params = [m['db_column_name'] for m in maps_resp.data]

# --- 5. GESTIONE IMPORT / EXPORT ---
with st.expander("📥 Manage Rooms (Bulk Import/Export)"):
    c1, c2 = st.columns(2)
    with c1:
        st.write("**Export Rooms**")
        rooms_raw = supabase.table("rooms").select("*").eq("project_id", project_id).order("room_number").execute()
        if rooms_raw.data:
            df_exp = pd.DataFrame([{
                "Number": r["room_number"], "Name": r["room_name_planned"], "Area": r.get("area"),
                **(r.get("parameters") or {})} for r in rooms_raw.data])
            buf = io.BytesIO()
            with pd.ExcelWriter(buf, engine='xlsxwriter') as writer: df_exp.to_excel(writer, index=False)
            st.download_button("⬇️ Download Excel", data=buf.getvalue(), file_name="rooms_sync.xlsx")

    with c2:
        st.write("**Import/Sync XLSX**")
        up_file = st.file_uploader("Upload XLSX", type=["xlsx"])
        if up_file and st.button("🚀 Start Bulk Sync"):
            df_up = pd.read_excel(up_file, dtype=str)
            bulk_data = []
            for _, row in df_up.iterrows():
                p_dict = {p: row[p] for p in mapped_params if p in row and pd.notna(row[p])}
                bulk_data.append({
                    "project_id": project_id, "room_number": str(row["Number"]).strip(),
                    "room_name_planned": str(row["Name"]), "parameters": p_dict, "is_synced": False})
            supabase.table("rooms").upsert(bulk_data, on_conflict="project_id,room_number").execute()
            st.success("Sync completato!"); st.rerun()

# --- 6. LOGICA ICONE 4 STATI ---
st.info("💡 **Status**: ✅ Sincronizzato | ⚠️ Modificato Web | ❗ Non in Revit | ❌ Mai Sincronizzato")

search_q = st.text_input("🔍 Filtra locali", placeholder="Cerca numero o nome...")
rooms_resp = supabase.table("rooms").select("*").eq("project_id", project_id).order("room_number").execute()

if rooms_resp.data:
    flat_data = []
    for r in rooms_resp.data:
        is_synced = r.get("is_synced") # True, False o None
        last_sync = r.get("last_sync_at")
        
        if is_synced is True: status_icon = "✅"
        elif is_synced is False and last_sync: status_icon = "⚠️"
        elif is_synced is None and last_sync: status_icon = "❗"
        else: status_icon = "❌"
            
        sync_str = pd.to_datetime(last_sync).strftime('%d/%m/%Y %H:%M') if last_sync else "Mai"
        
        row = {"id": int(r["id"]), "Status": status_icon, "Number": r["room_number"], 
               "Name": r["room_name_planned"], "Area (mq)": float(r.get("area") or 0), "Last_Sync": sync_str}
        p_json = r.get("parameters") or {}
        for p in mapped_params: row[p] = p_json.get(p, "")
        flat_data.append(row)
    
    df_display = pd.DataFrame(flat_data)
    if search_q:
        mask = df_display.apply(lambda x: x.astype(str).str.contains(search_q, case=False).any(), axis=1)
        df_display = df_display[mask].copy()

    df_display.insert(0, "Select", False)

    updated_df = st.data_editor(
        df_display, use_container_width=True, hide_index=True,
        column_config={
            "id": None, 
            "Status": st.column_config.TextColumn("Sync", width="small"),
            "Number": st.column_config.TextColumn("Room Number", disabled=True),
            "Area (mq)": st.column_config.NumberColumn("📐 Area", format="%.2f m²", disabled=True),
            "Last_Sync": st.column_config.TextColumn("Data Sync", disabled=True)
        },
        key="rooms_v3_editor"
    )

    if st.button("💾 SAVE ALL CHANGES", type="primary", use_container_width=True):
        success_count = 0
        for i in range(len(updated_df)):
            row_new = updated_df.iloc[i]; row_old = df_display.iloc[i]
            new_p = {p: row_new[p] for p in mapped_params}
            old_p = {p: row_old[p] for p in mapped_params}
            
            if (row_new["Name"] != row_old["Name"]) or (new_p != old_p):
                supabase.table("rooms").update({
                    "room_name_planned": row_new["Name"], "parameters": new_p,
                    "is_synced": False # Reset per forzare handshake Revit
                }).eq("id", int(row_new["id"])).execute()
                success_count += 1
        if success_count > 0:
            st.success(f"Aggiornati {success_count} locali."); st.rerun()
