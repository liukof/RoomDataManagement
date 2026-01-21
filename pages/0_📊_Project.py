import streamlit as st
import pandas as pd
import re
from app import supabase

st.set_page_config(page_title="Project Overview", layout="wide", page_icon="📊")

# 1. Controllo Accesso
if not st.session_state.get("user_data"):
    st.warning("⚠️ Esegui il login nella Home.")
    st.stop()

# --- INIZIALIZZAZIONE VARIABILI DI SICUREZZA ---
selected_project_name = "Tutti i Progetti"
target_project_id = None

# --- SIDEBAR: SELEZIONE PROGETTO ---
with st.sidebar:
    st.header("🏢 Filtri Progetto")
    try:
        # Carichiamo i progetti reali dal DB
        res_p = supabase.table("projects").select("id, name").execute()
        if res_p.data:
            project_options = {p['name']: p['id'] for p in res_p.data}
            names = list(project_options.keys())
            
            selected_name = st.selectbox("Seleziona Progetto", options=["Tutti"] + names)
            
            if selected_name != "Tutti":
                selected_project_name = selected_name
                target_project_id = project_options[selected_name]
        else:
            st.info("Nessun progetto trovato nel DB.")
    except Exception as e:
        st.error(f"Errore caricamento progetti: {e}")

st.title(f"📊 Riepilogo: {selected_project_name}")

# --- FUNZIONE DI RECUPERO DATI ---
@st.cache_data(ttl=600)
def fetch_filtered_data(project_id=None):
    try:
        # Query alla tabella 'rooms'
        query = supabase.table("rooms").select("*")
        if project_id:
            query = query.eq("project_id", project_id)
        
        res_rooms = query.execute()
        df_rooms = pd.DataFrame(res_rooms.data) if res_rooms.data else pd.DataFrame()
        
        total_area = 0.0
        df_display = pd.DataFrame()

        if not df_rooms.empty:
            # 1. Flattening del JSON 'parameters'
            if 'parameters' in df_rooms.columns:
                df_params = pd.json_normalize(df_rooms['parameters'])
                df_base = df_rooms.drop(columns=['parameters'])
                df_display = pd.concat([df_base, df_params], axis=1)
                
                # Rimuoviamo colonne duplicate (es. 'id' o 'created_at' se presenti nel JSON)
                df_display = df_display.loc[:, ~df_display.columns.duplicated()].copy()
                
                # 2. Calcolo Area
                # Cerchiamo colonne che contengono 'area' o 'superficie'
                area_col = next((c for c in df_display.columns if any(x in c.lower() for x in ['area', 'superficie'])), None)
                
                if area_col:
                    def clean_area(val):
                        if pd.isna(val) or val == "": return 0.0
                        # Estrae il primo numero trovato (gestisce 12.50, 12,50 mq, etc)
                        match = re.search(r'(\d+[.,]?\d*)', str(val))
                        if match:
                            return float(match.group(1).replace(',', '.'))
                        return 0.0
                    
                    total_area = df_display[area_col].apply(clean_area).sum()

        return {
            "rooms_count": len(df_rooms),
            "area_sum": total_area,
            "df_display": df_display,
            "error": None
        }
    except Exception as e:
        return {"rooms_count": 0, "area_sum": 0.0, "df_display": pd.DataFrame(), "error": str(e)}

# Esecuzione
with st.spinner("Analisi dati in corso..."):
    data = fetch_filtered_data(target_project_id)

if data["error"]:
    st.error(f"Errore durante l'analisi: {data['error']}")

# --- UI DASHBOARD ---
c1, c2, c3 = st.columns(3)
with c1:
    st.metric("📍 Locali", data["rooms_count"])
with c2:
    st.metric("📐 Superficie Totale", f"{data['area_sum']:,.2f} m²")
with c3:
    status = "Filtro Attivo" if target_project_id else "Visione Globale"
    st.metric("🔍 Stato Filtro", status)

st.divider()

# --- TABELLA DETTAGLIATA ---
if not data["df_display"].empty:
    st.subheader("📑 Elenco Locali")
    # Pulizia nomi colonne per una UX migliore (rimuove underscore)
    df_nice = data["df_display"].copy()
    df_nice.columns = [c.replace('_', ' ').title() for c in df_nice.columns]
    
    st.dataframe(df_nice, use_container_width=True, hide_index=True)
    
    # Bottone per scaricare i dati
    csv = df_nice.to_csv(index=False).encode('utf-8')
    st.download_button("📥 Scarica Report CSV", data=csv, file_name=f"report_{selected_project_name}.csv", mime='text/csv')
else:
    st.info("Nessun dato trovato per i criteri selezionati.")
