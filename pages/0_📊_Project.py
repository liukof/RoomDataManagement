import streamlit as st
import pandas as pd
import re
from app import supabase
import io

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
            name_col = find_column(df_p, ['project_code', 'name', 'project_name'])
            id_col = find_column(df_p, ['id', 'uuid'])
            
            if name_col and id_col:
                project_options = {row[name_col]: row[id_col] for _, row in df_p.iterrows()}
                selected_name = st.selectbox("Seleziona Progetto", options=["Tutti"] + list(project_options.keys()))
                
                if selected_name != "Tutti":
                    selected_project_name = selected_name
                    target_project_id = project_options[selected_name]
        else:
            st.info("Nessun progetto trovato.")
    except Exception as e:
        st.error("Errore nel caricamento progetti.")

st.title(f"📊 Riepilogo: {selected_project_name}")

# --- RECUPERO DATI ---
@st.cache_data(ttl=600)
def fetch_filtered_data(project_id=None):
    try:
        query = supabase.table("rooms").select("*")
        if project_id:
            query = query.eq("project_id", project_id)
        
        res_rooms = query.execute()
        df_rooms = pd.DataFrame(res_rooms.data) if res_rooms.data else pd.DataFrame()
        
        total_area = 0.0
        df_display = pd.DataFrame()

        if not df_rooms.empty:
            # 1. Espansione JSON parameters
            if 'parameters' in df_rooms.columns:
                # Normalizziamo il JSON
                df_params = pd.json_normalize(df_rooms['parameters'])
                df_base = df_rooms.drop(columns=['parameters'])
                # Concateniamo
                df_display = pd.concat([df_base, df_params], axis=1)
                
                # --- GESTIONE DUPLICATI COLONNE ---
                # Rimuoviamo colonne identiche (stesso nome, stessi dati)
                df_display = df_display.loc[:, ~df_display.columns.duplicated()].copy()
                
                # 2. Calcolo Area Dinamico
                area_col = find_column(df_display, ['area', 'superficie', 'mq'])
                
                if area_col:
                    def clean_area(val):
                        if pd.isna(val) or val == "": return 0.0
                        numbers = re.findall(r"[-+]?\d*\.\d+|\d+", str(val).replace(',', '.'))
                        return float(numbers[0]) if numbers else 0.0
                    
                    total_area = df_display[area_col].apply(clean_area).sum()

        return {"rooms_count": len(df_rooms), "area_sum": total_area, "df_display": df_display}
    except Exception as e:
        return {"rooms_count": 0, "area_sum": 0.0, "df_display": pd.DataFrame(), "error": str(e)}

data = fetch_filtered_data(target_project_id)

if "error" in data and data["error"]:
    st.error(f"Errore: {data['error']}")

# --- UI DASHBOARD ---
col1, col2, col3 = st.columns(3)
col1.metric("📍 Locali", data["rooms_count"])
col2.metric("📐 Superficie Totale", f"{data['area_sum']:,.2f} m²")
col3.metric("🔍 Filtro", "Attivo" if target_project_id else "Globale")

st.divider()

if not data["df_display"].empty:
    st.subheader("📑 Elenco Locali")
    
    df_nice = data["df_display"].copy()
    
    # --- FIX DUPLICATI DOPO PULIZIA NOMI ---
    # Creiamo nomi "belli" ma verifichiamo che non collidano
    new_cols = []
    seen = {}
    for c in df_nice.columns:
        nice_name = str(c).replace('_', ' ').title()
        if nice_name in seen:
            seen[nice_name] += 1
            new_cols.append(f"{nice_name} ({seen[nice_name]})")
        else:
            seen[nice_name] = 0
            new_cols.append(nice_name)
    
    df_nice.columns = new_cols
    
    # Visualizzazione
    st.dataframe(df_nice, use_container_width=True, hide_index=True)
else:
    st.info("Nessun dato disponibile per questo contesto.")
