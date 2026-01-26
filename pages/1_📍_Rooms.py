import streamlit as st
import pandas as pd
from supabase import create_client, Client
import io

# --- 1. SETUP & CONNESSIONE ---
try:
    url, key = st.secrets["SUPABASE_URL"], st.secrets["SUPABASE_KEY"]
except:
    st.error("Mancano le credenziali nei Secrets!")
    st.stop()

@st.cache_resource(ttl=3600)
def get_supabase_client() -> Client:
    return create_client(url, key)

supabase = get_supabase_client()

# --- 2. CONTROLLO ACCESSO & SIDEBAR (Semplificato) ---
if "user_data" not in st.session_state or st.session_state["user_data"] is None:
    st.switch_page("app.py")
    st.stop()

current_user = st.session_state["user_data"]
# (Logica per project_id basata sulla sidebar esistente)
# Assumiamo che project_id sia definito qui...

st.header("📍 Rooms & Sync Control")

# --- 3. LOGICA ICONE 4 STATI ---
st.info("💡 **Legenda**: ✅ Sincronizzato | ⚠️ Modificato Web | ❗ Non trovato in Revit | ❌ Mai Sincronizzato")

search_q = st.text_input("🔍 Filtra locali", placeholder="Cerca numero o nome...")
rooms_resp = supabase.table("rooms").select("*").eq("project_id", project_id).order("room_number").execute()

if rooms_resp.data:
    flat_data = []
    for r in rooms_resp.data:
        is_synced = r.get("is_synced") # Può essere True, False o None
        last_sync = r.get("last_sync_at")
        
        # LOGICA 4 STATI
        if is_synced is True:
            status_icon = "✅" # Handshake riuscito
        elif is_synced is False and last_sync:
            status_icon = "⚠️" # Modificato sul web dopo sync
        elif is_synced is None and last_sync:
            status_icon = "❗" # DISALLINEATO (Non trovato in Revit)
        else:
            status_icon = "❌" # Nuovo locale
            
        sync_str = pd.to_datetime(last_sync).strftime('%d/%m/%Y %H:%M') if last_sync else "Mai"
        
        row = {
            "id": int(r["id"]), 
            "Status": status_icon,
            "Number": r["room_number"], 
            "Name": r["room_name_planned"], 
            "Area (mq)": float(r.get("area") or 0),
            "Last_Sync": sync_str
        }
        # (Logica parametri mappati...)
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
            "Status": st.column_config.TextColumn("Sync", width="small", help="✅ OK | ⚠️ Edit Web | ❗ Errore Revit | ❌ Nuovo"),
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
            # (Confronto parametri...)
            # Se cambiato:
            supabase.table("rooms").update({
                "room_name_planned": row_new["Name"],
                "is_synced": False # Reset su modifica web
            }).eq("id", int(row_new["id"])).execute()
            success_count += 1
        if success_count > 0:
            st.success("Modifiche salvate."); st.rerun()
