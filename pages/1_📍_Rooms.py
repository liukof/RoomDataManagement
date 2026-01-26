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

# --- 3. SIDEBAR & PROGETTO ---
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

# --- 5. LOGICA 3 STATI (Matrix) ---
st.info("💡 **Status**: ✅ Sincronizzato | ⚠️ Modificato sul Web | ❌ Mai Sincronizzato")

# --- 6. TABELLA EDITABILE ---
search_q = st.text_input("🔍 Cerca locale...", placeholder="Numero o Nome")
rooms_resp = supabase.table("rooms").select("*").eq("project_id", project_id).order("room_number").execute()

if rooms_resp.data:
    flat_data = []
    for r in rooms_resp.data:
        is_synced = r.get("is_synced", False)
        last_sync = r.get("last_sync_at")
        
        # Determinazione Icona
        if is_synced: status_icon = "✅"
        elif last_sync: status_icon = "⚠️"
        else: status_icon = "❌"
            
        sync_str = pd.to_datetime(last_sync).strftime('%d/%m/%Y %H:%M') if last_sync else "Mai"
        
        row = {
            "id": int(r["id"]), 
            "Status": status_icon,
            "DB_Sync": sync_str,
            "Number": r["room_number"], 
            "Name": r["room_name_planned"], 
            "Area (mq)": float(r.get("area") or 0)
        }
        p_json = r.get("parameters") or {}
        for p in mapped_params: row[p] = p_json.get(p, "")
        flat_data.append(row)
    
    df_display = pd.DataFrame(flat_data)
    if search_q:
        mask = df_display.apply(lambda x: x.astype(str).str.contains(search_q, case=False).any(), axis=1)
        df_display = df_display[mask]

    df_display.insert(0, "Select", False)

    updated_df = st.data_editor(
        df_display,
        use_container_width=True,
        hide_index=True,
        column_config={
            "id": None, 
            "Status": st.column_config.TextColumn("Sync", width="small"),
            "DB_Sync": st.column_config.TextColumn("Last Sync", width="medium"),
            "Area (mq)": st.column_config.NumberColumn("📐 Area", format="%.2f m²", disabled=True),
            "Select": st.column_config.CheckboxColumn("Sel.")
        },
        key="rooms_v3_editor"
    )

    if st.button("💾 SAVE ALL CHANGES", type="primary", use_container_width=True):
        success_count = 0
        for i in range(len(updated_df)):
            row_new = updated_df.iloc[i]
            row_old = df_display.iloc[i]
            
            new_params = {p: row_new[p] for p in mapped_params}
            old_params = {p: row_old[p] for p in mapped_params}
            
            if (row_new["Number"] != row_old["Number"]) or (row_new["Name"] != row_old["Name"]) or (new_params != old_params):
                supabase.table("rooms").update({
                    "room_number": row_new["Number"],
                    "room_name_planned": row_new["Name"],
                    "parameters": new_params,
                    "is_synced": False # Reset su ogni modifica
                }).eq("id", int(row_new["id"])).execute()
                success_count += 1
        if success_count > 0:
            st.success(f"Aggiornati {success_count} locali."); st.rerun()
