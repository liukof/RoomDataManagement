import streamlit as st
import pandas as pd
from app import supabase

st.set_page_config(page_title="Project Overview", layout="wide", page_icon="📊")

if not st.session_state.get("user_data"):
    st.warning("⚠️ Esegui il login nella Home.")
    st.stop()

st.title("📊 Riepilogo Commessa BIM")

@st.cache_data(ttl=600)
def fetch_project_kpis():
    try:
        # 1. Recupero conteggi base
        r_rooms = supabase.table("rooms").select("id", count="exact").execute()
        r_items = supabase.table("items").select("id", count="exact").execute()
        r_projs = supabase.table("projects").select("id", count="exact").execute()
        
        # 2. Recupero dati per analisi dinamica colonne
        # Selezioniamo solo 1 riga per vedere i nomi delle colonne ed evitare l'errore 42703
        sample_room = supabase.table("rooms").select("*").limit(1).execute()
        
        total_area = 0.0
        if sample_room.data:
            df_sample = pd.DataFrame(sample_room.data)
            # Cerchiamo una colonna che somigli a "area" (case-insensitive)
            area_col = next((c for c in df_sample.columns if 'area' in c.lower()), None)
            
            if area_col:
                # Se troviamo la colonna, recuperiamo tutti i valori di quella colonna
                all_areas = supabase.table("rooms").select(area_col).execute()
                df_areas = pd.DataFrame(all_areas.data)
                total_area = pd.to_numeric(df_areas[area_col], errors='coerce').sum()

        return {
            "rooms": r_rooms.count or 0,
            "items": r_items.count or 0,
            "projects": r_projs.count or 0,
            "area": total_area,
            "error": None
        }
    except Exception as e:
        return {"rooms": 0, "items": 0, "projects": 0, "area": 0, "error": str(e)}

stats = fetch_project_kpis()

if stats["error"]:
    st.error(f"Dettaglio Errore: {stats['error']}")

# --- UI DASHBOARD ---
c1, c2, c3, c4 = st.columns(4)

with c1:
    st.metric("📍 Totale Locali", stats["rooms"])
with c2:
    st.metric("📦 Oggetti/Items", stats["items"])
with c3:
    st.metric("📐 Superficie Totale", f"{stats['area']:,.2f} m²")
with c4:
    st.metric("🏢 Progetti Attivi", stats["projects"])

st.divider()

# --- ISPEZIONE DATI ---
st.subheader("🗂️ Ispezione Tabelle (Anteprima)")
tab1, tab2, tab3 = st.tabs(["Locali", "Catalogo", "Progetti"])

with tab1:
    res = supabase.table("rooms").select("*").limit(10).execute()
    if res.data:
        st.dataframe(pd.DataFrame(res.data), use_container_width=True)
    else:
        st.info("La tabella 'rooms' è vuota.")

with tab2:
    res = supabase.table("items").select("*").limit(10).execute()
    if res.data:
        st.dataframe(pd.DataFrame(res.data), use_container_width=True)
    else:
        st.info("La tabella 'items' è vuota.")

with tab3:
    res = supabase.table("projects").select("*").limit(10).execute()
    if res.data:
        st.dataframe(pd.DataFrame(res.data), use_container_width=True)
    else:
        st.info("La tabella 'projects' è vuota.")
