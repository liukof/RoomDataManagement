import streamlit as st
import pandas as pd
from app import supabase

st.set_page_config(page_title="Project Overview", layout="wide", page_icon="📊")

if st.session_state.get("user_data") is None:
    st.warning("⚠️ Effettua il login nella Home.")
    st.stop()

st.title("📊 Riepilogo Commessa BIM")

@st.cache_data(ttl=300)
def get_stats():
    # --- TENTATIVO DI RECUPERO DATI CON GESTIONE ERRORI ---
    try:
        # 1. Prova a leggere la tabella delle stanze (cambia "Rooms" se necessario)
        # Usiamo select("*") inizialmente per evitare errori su colonne specifiche come "area"
        r_rooms = supabase.table("Rooms").select("*", count="exact").execute()
        
        # 2. Prova a leggere il catalogo (cambia "ItemCatalog" se necessario)
        r_items = supabase.table("ItemCatalog").select("*", count="exact").execute()
        
        # Calcolo area sicuro (controlla se la colonna esiste, altrimenti usa 0)
        df_rooms = pd.DataFrame(r_rooms.data)
        area_col = 'Area' if 'Area' in df_rooms.columns else ('area' if 'area' in df_rooms.columns else None)
        
        total_area = 0
        if area_col:
            total_area = df_rooms[area_col].astype(float).sum()

        return {
            "count_rooms": r_rooms.count if r_rooms.count else 0,
            "count_items": r_items.count if r_items.count else 0,
            "total_area": total_area,
            "error": None
        }
    except Exception as e:
        return {
            "count_rooms": 0, "count_items": 0, "total_area": 0,
            "error": str(e)
        }

with st.spinner("Sincronizzazione con il database BIM..."):
    data = get_stats()

if data["error"]:
    st.error(f"❌ Errore di connessione alle tabelle: {data['error']}")
    st.info("💡 Verifica che i nomi delle tabelle in Supabase siano 'Rooms' e 'ItemCatalog'. Se sono diversi, modifica lo script.")
else:
    # --- UI DASHBOARD ---
    c1, c2, c3 = st.columns(3)
    with c1:
        st.metric("📍 Locali Totali", data["count_rooms"])
    with c2:
        st.metric("📦 Oggetti in Catalogo", data["count_items"])
    with c3:
        st.metric("📐 Superficie Totale", f"{data['total_area']:.2f} m²")

st.divider()
