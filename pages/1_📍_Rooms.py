import streamlit as st
import pandas as pd
from supabase import create_client, Client
import io

# --- 1. SETUP & CONNESSIONE ---
try:
    url = st.secrets["https://zegdtlkmfgoieuprbruz.supabase.co"]
    key = st.secrets["eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJpc3MiOiJzdXBhYmFzZSIsInJlZiI6InplZ2R0bGttZmdvaWV1cHJicnV6Iiwicm9sZSI6ImFub24iLCJpYXQiOjE3NjY2OTY2NjIsImV4cCI6MjA4MjI3MjY2Mn0.SziiUnoXdGtzb1IRUSMnvBkfNPNqVAaeK1IQW5v31do"]
except KeyError:
    st.error("Configurazione mancante nei Secrets! (SUPABASE_URL, SUPABASE_KEY)")
    st.stop()

@st.cache_resource(ttl=3600)
def get_supabase_client() -> Client:
    return create_client(url, key)

supabase = get_supabase_client()

# --- 2. CONTROLLO ACCESSO ---
if "user_data" not in st.session_state or st.session_state["user_data"] is None:
    st.warning("⚠️ Effettua il login per accedere.")
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

# Recupero progetti autorizzati per definire il project_id
query_p = supabase.table("projects").select("*").order("project_code")
if not is_admin:
    query_p = query_p.in_("id", allowed_ids if allowed_ids else [0])
projects_list = query_p.execute().data

# Inizializziamo project_id a None
project_id = None

if projects_list:
    project_options = {f"{p['project_code']} - {p['project_name']}": p['id'] for p in projects_list}
    selected_label = st.sidebar.selectbox("Current Project Context:", list(project_options.keys()))
    project_id = int(project_options[selected_label])
else:
    st.error("Nessun progetto assegnato.")
    st.stop()

# --- 4. DATA FETCHING (ROOMS & MAPPINGS) ---
st.header("📍 Rooms & Sync Control")
st.info("💡 **Status**: ✅ Sincronizzato | ⚠️ Modificato Web | ❌ Mai Sincronizzato")

# Recupero mapping parametri
maps_resp = supabase.table("parameter_mappings").select("db_column_name").eq("project_id", project_id).execute()
mapped_params = [m['db_column_name'] for m in maps_resp.data]

# --- 5. LOGICA TABELLA ---
search_q = st.text_input("🔍 Filter Rooms", placeholder="Cerca numero o nome...")
rooms_resp = supabase.table("rooms").select("*").eq("project_id", project_id).order("room_number").execute()

if rooms_resp.data:
    flat_data = []
    for r in rooms_resp.data:
        is_synced = r.get("is_synced", False)
        last_sync = r.get("last_sync_at")
        
        # Logica 3 stati
        if is_synced:
            status_icon = "✅"
        elif last_sync:
            status_icon = "⚠️"
        else:
            status_icon = "❌"
            
        sync_str = pd.to_datetime(last_sync).strftime('%d/%m/%Y %H:%M') if last_sync else "Mai"
        
        row = {
            "id": int(r["id"]), 
            "Status": status_icon,
            "Number": r["room_number"], 
            "Name": r["room_name_planned"], 
            "Area (mq)": float(r.get("area") or 0),
            "Last_Sync": sync_str
        }
        p_json = r.get("parameters") or {}
        for p in mapped_params:
            row[p] = p_json.get(p, "")
        flat_data.append(row)
    
    df_display = pd.DataFrame(flat_data)
    if search_q:
        mask = df_display.apply(lambda x: x.astype(str).str.contains(search_q, case=False).any(), axis=1)
        df_display = df_display[mask].copy()

    df_display.insert(0, "Select", False)

    # Configurazione data_editor
    updated_df = st.data_editor(
        df_display,
        use_container_width=True,
        hide_index=True,
        column_config={
            "id": None, 
            "Status": st.column_config.TextColumn("Sync", width="small", help="✅ OK | ⚠️ Da aggiornare | ❌ Nuovo"),
            "Number": st.column_config.TextColumn("Room Number", disabled=True),
            "Area (mq)": st.column_config.NumberColumn("📐 Area", format="%.2f m²", disabled=True),
            "Last_Sync": st.column_config.TextColumn("Data Sync", disabled=True)
        },
        key="rooms_v3_editor"
    )

    # --- SALVATAGGIO MODIFICHE ---
    if st.button("💾 SAVE ALL CHANGES", type="primary", use_container_width=True):
        success_count = 0
        for i in range(len(updated_df)):
            row_new = updated_df.iloc[i]
            row_old = df_display.iloc[i]
            
            new_p = {p: row_new[p] for p in mapped_params}
            old_p = {p: row_old[p] for p in mapped_params}
            
            if (row_new["Name"] != row_old["Name"]) or (new_p != old_p):
                supabase.table("rooms").update({
                    "room_name_planned": row_new["Name"],
                    "parameters": new_p,
                    "is_synced": False # Reset stato per Handshake Revit
                }).eq("id", int(row_new["id"])).execute()
                success_count += 1
        
        if success_count > 0:
            st.success(f"Aggiornati {success_count} locali. Stato Sync resettato.")
            st.rerun()

# --- 6. ITEM CATALOG PREVIEW (NEXT STEP) ---
st.divider()
st.subheader("📦 Item Catalog Management")
st.info("Questa sezione permetterà di gestire gli arredi associati ai locali sopra selezionati.")
