import streamlit as st
import pandas as pd
from supabase import create_client, Client
import io

# --- 1. SETUP & CONNESSIONE ---
try:
    url, key = st.secrets["SUPABASE_URL"], st.secrets["SUPABASE_KEY"]
except:
    st.error("Configurazione mancante!")
    st.stop()

@st.cache_resource(ttl=3600)
def get_supabase_client() -> Client:
    return create_client(url, key)

supabase = get_supabase_client()

# --- 2. CONTROLLO ACCESSO & SIDEBAR (Omettiamo per brevità, mantieni esistente) ---
# ... (Inserisci qui il blocco di autenticazione e sidebar)

# --- 3. RECUPERO DATI E LOGICA 3 STATI ---
st.header("📍 Rooms & Sync Control")
st.info("💡 **Status**: ✅ Sincronizzato | ⚠️ Modificato Web | ❌ Mai Sincronizzato")

search_q = st.text_input("🔍 Cerca locale...", placeholder="Numero o Nome")
rooms_resp = supabase.table("rooms").select("*").eq("project_id", project_id).order("room_number").execute()

if rooms_resp.data:
    flat_data = []
    for r in rooms_resp.data:
        is_synced = r.get("is_synced", False)
        last_sync = r.get("last_sync_at")
        
        # LOGICA 3 STATI
        if is_synced: status_icon = "✅"
        elif last_sync: status_icon = "⚠️"
        else: status_icon = "❌"
            
        sync_str = pd.to_datetime(last_sync).strftime('%d/%m/%Y %H:%M') if last_sync else "Mai"
        
        row = {
            "id": int(r["id"]), 
            "Status": status_icon,
            "Number": r["room_number"], 
            "Name": r["room_name_planned"], 
            "Area (mq)": float(r.get("area") or 0),
            "Last_Sync_Handshake": sync_str
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
            "Number": st.column_config.TextColumn("Room Number", disabled=True),
            "Area (mq)": st.column_config.NumberColumn("📐 Area", format="%.2f m²", disabled=True),
            "Last_Sync_Handshake": st.column_config.TextColumn("Ultima Sync", disabled=True)
        },
        key="rooms_v3_editor"
    )

    if st.button("💾 SAVE ALL CHANGES", type="primary", use_container_width=True):
        # ... (Logica di confronto identica alla precedente)
        # IMPORTANTE: In caso di modifica impostare is_synced = False
        # per far passare l'icona da ✅ a ⚠️
        st.success("Modifiche salvate. Stato Sync resettato per i locali modificati.")
        st.rerun()
