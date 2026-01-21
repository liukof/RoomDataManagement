import streamlit as st
import pandas as pd
from app import supabase

st.set_page_config(page_title="Project Overview", layout="wide", page_icon="📊")

if not st.session_state.get("user_data"):
    st.warning("⚠️ Esegui il login nella Home.")
    st.stop()

st.title("📊 Riepilogo Commessa BIM")

@st.cache_data(ttl=600)
def fetch_and_clean_data():
    try:
        # Recupero record
        res_rooms = supabase.table("rooms").select("*").execute()
        res_items = supabase.table("items").select("id", count="exact").execute()
        res_projs = supabase.table("projects").select("id", count="exact").execute()
        
        df_rooms = pd.DataFrame(res_rooms.data)
        
        total_area = 0.0
        
        if not df_rooms.empty and 'parameters' in df_rooms.columns:
            # --- LOGICA DI COERENZA VISIVA ---
            # Espandiamo il campo JSON 'parameters' in colonne separate
            df_params = pd.json_normalize(df_rooms['parameters'])
            
            # Uniamo le colonne originali (id, created_at) con quelle estratte dal JSON
            df_final = pd.concat([df_rooms.drop(columns=['parameters']), df_params], axis=1)
            
            # Cerchiamo l'area dentro i parametri estratti
            area_col = next((c for c in df_final.columns if 'area' in c.lower()), None)
            if area_col:
                # Pulizia stringhe (es. rimuove " m²" se presente) e conversione
                total_area = pd.to_numeric(
                    df_final[area_col].astype(str).str.replace(',', '.').str.extract('(\d+\.?\d*)')[0], 
                    errors='coerce'
                ).sum()
        else:
            df_final = df_rooms

        return {
            "rooms_count": len(df_rooms),
            "items_count": res_items.count or 0,
            "projects_count": res_projs.count or 0,
            "area_sum": total_area,
            "df_display": df_final,
            "error": None
        }
    except Exception as e:
        return {"rooms_count": 0, "items_count": 0, "projects_count": 0, "area_sum": 0, "df_display": pd.DataFrame(), "error": str(e)}

with st.spinner("Sincronizzazione coerente dei dati..."):
    data = fetch_and_clean_data()

# --- DASHBOARD KPI ---
c1, c2, c3, c4 = st.columns(4)
c1.metric("📍 Locali Totali", data["rooms_count"])
c2.metric("📦 Oggetti/Items", data["items_count"])
c3.metric("📐 Superficie Totale", f"{data['area_sum']:,.2f} m²")
c4.metric("🏢 Progetti Attivi", data["projects_count"])

st.divider()

# --- VISUALIZZAZIONE COERENTE ---
st.subheader("📑 Anteprima Dati (Formattazione App)")
if not data["df_display"].empty:
    # Mostriamo la tabella "pulita" senza il campo JSON grezzo
    st.dataframe(data["df_display"], use_container_width=True)
else:
    st.info("Nessun dato disponibile nelle tabelle selezionate.")
