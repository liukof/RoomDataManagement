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
    # Recupero dati dalle tue tabelle esistenti
    r_rooms = supabase.table("locali").select("id, area", count="exact").execute()
    r_items = supabase.table("catalogo_oggetti").select("id", count="exact").execute()
    
    stats = {
        "count_rooms": r_rooms.count if r_rooms.count else 0,
        "count_items": r_items.count if r_items.count else 0,
        "total_area": sum([float(i.get('area', 0)) for i in r_rooms.data]) if r_rooms.data else 0
    }
    return stats

with st.spinner("Caricamento statistiche..."):
    data = get_stats()

# --- UI DASHBOARD ---
c1, c2, c3 = st.columns(3)
with c1:
    st.container(border=True).metric("📍 Locali Totali", data["count_rooms"])
with c2:
    st.container(border=True).metric("📦 Oggetti in Catalogo", data["count_items"])
with c3:
    st.container(border=True).metric("📐 Superficie Totale", f"{data['total_area']:.2f} m²")

st.divider()

# Visualizzazione rapida stato avanzamento
st.subheader("🚀 Stato del Modello")
col_left, col_right = st.columns(2)

with col_left:
    st.info("**Update Recenti:**\nIl database è sincronizzato con l'ultimo export di Revit.")
    if st.button("🔄 Forza Aggiornamento Cache"):
        st.cache_data.clear()
        st.rerun()

with col_right:
    # Esempio di grafico rapido
    st.write("Distribuzione Aree")
    # Qui potresti inserire un grafico basato sui dati reali
