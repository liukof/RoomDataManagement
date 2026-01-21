import streamlit as st
import pandas as pd
import re
from app import supabase

st.set_page_config(page_title="Project Overview", layout="wide", page_icon="📊")

if not st.session_state.get("user_data"):
    st.warning("⚠️ Esegui il login nella Home.")
    st.stop()

# --- FUNZIONE AUSILIARIA PER TROVARE COLONNE ---
def find_column(df, possible_names):
    for name in possible_names:
        found = next((c for c in df.columns if name.lower() in c.lower()), None)
        if found: return found
    return None

# --- INIZIALIZZAZIONE ---
selected_project_name = "Tutti i Progetti"
target_project_id = None

# --- SIDEBAR: SELEZIONE PROGETTO ---
with st.sidebar:
    st.header("🏢 Filtri Progetto")
    try:
        res_p = supabase.table("projects").select("*").execute()
        if res_p.data:
            df_p = pd.DataFrame(res_p.data)
            # Cerchiamo la colonna del nome (name, project_name, titolo...)
            name_col = find_column(df_p, ['name', 'nom', 'titolo', 'label'])
            id_col = find_column(df_p, ['id', 'uuid', 'pk'])
            
            if name_col and id_col:
                project_options = {row[name_col]: row[id_col] for _, row in df_p.iterrows()}
                selected_name = st.selectbox("Seleziona Progetto", options=["Tutti"] + list(project_options.keys()))
                
                if selected_name != "Tutti":
                    selected_project_name = selected_name
                    target_project_id = project_options[selected_name]
        else:
            st.info("Nessun progetto trovato.")
    except Exception as e:
        st.error(f"Nota: Configura la tabella 'projects' con una colonna 'name'.")

st.title(f"📊 Riepilogo: {selected_project_name}")

# --- RECUPERO DATI ---
@st.cache_data(ttl=600)
def fetch_filtered_data(project_id=None):
    try:
        query = supabase.table("rooms").select("*")
        if project_id:
            # Cerchiamo di capire se la colonna è project_id o id_progetto
            query = query.eq("project_id", project_id)
        
        res_rooms = query.execute()
        df_rooms = pd.DataFrame(res_rooms.data) if res_rooms.data else pd.DataFrame()
        
        total_area = 0.0
        df_display = pd.DataFrame()

        if not df_rooms.empty:
            # 1. Espansione JSON parameters
            if 'parameters' in df_rooms.columns:
                df_params = pd.json_normalize(df_rooms['parameters'])
                df_base = df_rooms.drop(columns=['parameters'])
                df_display = pd.concat([df_base, df_params], axis=1)
                df_display = df_display.loc[:, ~df_display.columns.duplicated()].copy()
                
                # 2. Calcolo Area Dinamico
                area_col = find_column(df_display, ['area', 'superficie', 'sqm', 'mq'])
                
                if area_col:
                    def clean_area(val):
                        if pd.isna(val) or val == "": return 0.0
                        # Estrazione numerica avanzata
                        numbers = re.findall(r"[-+]?\d*\.\d+|\d+", str(val).replace(',', '.'))
                        return float(numbers[0]) if numbers else 0.0
                    
                    total_area = df_display[area_col].apply(clean_area).sum()

        return {"rooms_count": len(df_rooms), "area_sum": total_area, "df_display": df_display, "error": None}
    except Exception as e:
        return {"rooms_count": 0, "area_sum": 0.0, "df_display": pd.DataFrame(), "error": str(e)}

data = fetch_filtered_data(target_project_id)

# --- UI DASHBOARD ---

col1, col2, col3 = st.columns(3)
col1.metric("📍 Locali", data["rooms_count"])
col2.metric("📐 Superficie Totale", f"{data['area_sum']:,.2f} m²")
col3.metric("🔍 Filtro", "Attivo" if target_project_id else "Globale")

st.divider()

if not data["df_display"].empty:
    st.subheader("📑 Elenco Locali")
    # Pulizia nomi colonne per visualizzazione
    df_nice = data["df_display"].copy()
    df_nice.columns = [c.replace('_', ' ').title() for c in df_nice.columns]
    st.dataframe(df_nice, use_container_width=True, hide_index=True)
else:
    st.info("In attesa di dati o nessun locale corrispondente trovato.")
