import streamlit as st
import pandas as pd
from app import supabase

st.set_page_config(page_title="Project Overview", layout="wide", page_icon="📊")

if not st.session_state.get("user_data"):
    st.warning("⚠️ Esegui il login nella Home.")
    st.stop()

# --- SIDEBAR: SELEZIONE PROGETTO ---
with st.sidebar:
    st.header("Filtri Progetto")
    # Recuperiamo la lista dei progetti per il selettore
    try:
        res_p = supabase.table("projects").select("id, name").execute()
        projects_list = res_p.data if res_p.data else []
        project_options = {p['name']: p['id'] for p in projects_list}
        
        selected_project_name = st.selectbox("Seleziona Progetto", options=["Tutti"] + list(project_options.keys()))
        target_project_id = project_options.get(selected_project_name)
    except:
        st.error("Errore nel caricamento progetti")
        target_project_id = None

st.title(f"📊 Riepilogo: {selected_project_name}")

@st.cache_data(ttl=600)
def fetch_filtered_data(project_id=None):
    try:
        # 1. Query filtrata se è selezionato un progetto specifico
        query = supabase.table("rooms").select("*")
        if project_id:
            query = query.eq("project_id", project_id) # Assicurati che la colonna sia 'project_id'
        
        res_rooms = query.execute()
        df_rooms = pd.DataFrame(res_rooms.data)
        
        total_area = 0.0
        df_display = pd.DataFrame()

        if not df_rooms.empty:
            # --- FIX DUPLICATI E FLATTENING ---
            if 'parameters' in df_rooms.columns:
                # Estraiamo i parametri
                df_params = pd.json_normalize(df_rooms['parameters'])
                
                # Rimuoviamo la colonna 'parameters' originale
                df_base = df_rooms.drop(columns=['parameters'])
                
                # Risoluzione nomi duplicati aggiungendo un prefisso ai parametri se necessario
                # In questo caso, forziamo nomi unici
                df_display = pd.concat([df_base, df_params], axis=1)
                df_display = df_display.loc[:, ~df_display.columns.duplicated()].copy()
                
                # --- CALCOLO AREA ---
                area_col = next((c for c in df_display.columns if 'area' in c.lower()), None)
                if area_col:
                    # Pulizia e somma
                    def clean_area(val):
                        if pd.isna(val) or val == "": return 0
                        import re
                        match = re.search(r'(\d+[.,]?\d*)', str(val))
                        return float(match.group(1).replace(',', '.')) if match else 0
                    
                    total_area = df_display[area_col].apply(clean_area).sum()

        return {
            "rooms_count": len(df_rooms),
            "area_sum": total_area,
            "df_display": df_display,
            "error": None
        }
    except Exception as e:
        return {"rooms_count": 0, "area_sum": 0, "df_display": pd.DataFrame(), "error": str(e)}

# Caricamento dati basato sul filtro
data = fetch_filtered_data(target_project_id)

# --- DASHBOARD KPI ---
c1, c2, c3 = st.columns(3)
with c1:
    st.metric("📍 Locali nel Progetto", data["rooms_count"])
with c2:
    st.metric("📐 Superficie Totale", f"{data['area_sum']:,.2f} m²")
with c3:
    st.metric("📂 ID Progetto", target_project_id if target_project_id else "Global")

st.divider()

# --- TABELLA COERENTE ---
if not data["df_display"].empty:
    st.subheader("📑 Dati Dettagliati Locali")
    st.dataframe(data["df_display"], use_container_width=True)
else:
    st.info("Nessun locale trovato per questo progetto.")
