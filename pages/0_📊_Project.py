import streamlit as st
import pandas as pd
from app import supabase

st.set_page_config(page_title="Project Overview", layout="wide", page_icon="📊")

if not st.session_state.get("user_data"):
    st.warning("Esegui il login nella Home.")
    st.stop()

st.title("📊 Riepilogo Commessa BIM")

@st.cache_data(ttl=600)
def fetch_project_kpis():
    try:
        # Conteggio reale dalle tue tabelle in Supabase
        r_rooms = supabase.table("rooms").select("id", count="exact").execute()
        r_items = supabase.table("items").select("id", count="exact").execute()
        r_projs = supabase.table("projects").select("id", count="exact").execute()
        
        # Recupero dati per calcolo aree (assumendo colonna 'area' in 'rooms')
        data_rooms = supabase.table("rooms").select("area").execute()
        df_rooms = pd.DataFrame(data_rooms.data)
        
        total_area = 0
        if not df_rooms.empty and 'area' in df_rooms.columns:
            total_area = pd.to_numeric(df_rooms['area'], errors='coerce').sum()

        return {
            "rooms": r_rooms.count or 0,
            "items": r_items.count or 0,
            "projects": r_projs.count or 0,
            "area": total_area
        }
    except Exception as e:
        st.error(f"Errore DB: {e}")
        return {"rooms": 0, "items": 0, "projects": 0, "area": 0}

stats = fetch_project_kpis()

# --- INTERFACCIA GRAFICA ---
st.subheader("Key Performance Indicators")
c1, c2, c3, c4 = st.columns(4)

with c1:
    st.container(border=True).metric("📍 Totale Locali", stats["rooms"])
with c2:
    st.container(border=True).metric("📦 Oggetti/Items", stats["items"])
with c3:
    st.container(border=True).metric("📐 Superficie (mq)", f"{stats['area']:,.2f}")
with c4:
    st.container(border=True).metric("🏢 Progetti Attivi", stats["projects"])

st.divider()

# Visualizzazione rapida delle tabelle attive
st.subheader("🗂️ Struttura Dati Rilevata")
tabs = st.tabs(["Rooms Data", "Item Catalog", "Project Info"])

with tabs[0]:
    raw_rooms = supabase.table("rooms").select("*").limit(5).execute()
    st.dataframe(pd.DataFrame(raw_rooms.data), use_container_width=True)

with tabs[1]:
    raw_items = supabase.table("items").select("*").limit(5).execute()
    st.dataframe(pd.DataFrame(raw_items.data), use_container_width=True)

with tabs[2]:
    raw_projects = supabase.table("projects").select("*").limit(5).execute()
    st.dataframe(pd.DataFrame(raw_projects.data), use_container_width=True)
