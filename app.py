import streamlit as st
import pandas as pd
from supabase import create_client, Client
import io

# --- SETUP SUPABASE ---
url = st.secrets["SUPABASE_URL"]
key = st.secrets["SUPABASE_KEY"]
supabase: Client = create_client(url, key)

st.set_page_config(page_title="BIM Data Manager PRO", layout="wide")

# --- RECUPERO PROGETTI ---
projects_resp = supabase.table("projects").select("*").execute()
projects_list = projects_resp.data

# --- NAVIGAZIONE ---
menu = st.sidebar.radio("Menu", ["Locali", "Mappatura Parametri", "Gestione Progetti"])

if menu in ["Locali", "Mappatura Parametri"]:
    project_options = {f"{p['project_code']} - {p['project_name']}": p for p in projects_list}
    selected_label = st.sidebar.selectbox("Progetto:", list(project_options.keys()))
    project_id = project_options[selected_label]['id']

    # --- PAGINA LOCALI (LOGICA JSONB) ---
    if menu == "Locali":
        st.title(f"📍 Locali - {selected_label}")
        
        # 1. Recuperiamo i mapping per sapere quali parametri mostrare
        maps_resp = supabase.table("parameter_mappings").select("db_column_name").eq("project_id", project_id).execute()
        mapped_params = [m['db_column_name'] for m in maps_resp.data]

        # 2. Recuperiamo i locali
        rooms_resp = supabase.table("rooms").select("*").eq("project_id", project_id).order("room_number").execute()
        
        if rooms_resp.data:
            # Trasformiamo i dati JSONB in colonne piatte per l'editor
            flat_data = []
            for r in rooms_resp.data:
                row = {
                    "id": r["id"],
                    "room_number": r["room_number"],
                    "room_name_planned": r["room_name_planned"]
                }
                # Estraiamo i valori dal campo JSONB 'parameters'
                db_params = r.get("parameters") or {}
                for p_name in mapped_params:
                    row[p_name] = db_params.get(p_name, "")
                flat_data.append(row)

            df_rooms = pd.DataFrame(flat_data)

            st.subheader("📝 Editor Parametri Dinamici")
            edited_df = st.data_editor(
                df_rooms,
                column_config={"id": None, "room_number": st.column_config.TextColumn("Numero", disabled=True)},
                use_container_width=True, hide_index=True, key="json_editor"
            )

            if st.button("💾 Salva in JSONB"):
                for _, row in edited_df.iterrows():
                    # Ricostruiamo l'oggetto JSONB con i nuovi valori
                    new_params = {p: row[p] for p in mapped_params if p in row}
                    supabase.table("rooms").update({
                        "room_name_planned": row["room_name_planned"],
                        "parameters": new_params
                    }).eq("id", row["id"]).execute()
                st.success("Dati salvati nel campo JSONB!")
                st.rerun()

    # --- PAGINA MAPPATURA (Invariata ma fondamentale) ---
    elif menu == "Mappatura Parametri":
        st.title("🔗 Mappatura Parametri")
        # (Inserisci qui il codice della mappatura che avevi prima)
        # L'unica differenza è che 'db_column_name' ora si riferisce a una chiave nel JSON
        st.info("I nomi inseriti qui diventeranno automaticamente campi nel JSONB dei locali.")
        # ... (codice form mappatura)
