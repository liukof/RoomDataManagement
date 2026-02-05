import streamlit as st
import pandas as pd
from supabase import create_client, Client
import io

# --- 1. SETUP & CONNESSIONE ---
try:
    url = st.secrets["SUPABASE_URL"]
    key = st.secrets["SUPABASE_KEY"]
except KeyError:
    st.error("Configurazione mancante nei Secrets! (SUPABASE_URL, SUPABASE_KEY)")
    st.stop()

@st.cache_resource(ttl=3600)
def get_supabase_client() -> Client:
    return create_client(url, key)

supabase = get_supabase_client()

# --- 2. CONTROLLO ACCESSO ---
if "user_data" not in st.session_state or st.session_state["user_data"] is None:
    st.warning("⚠️ Effettua il login per accedere.")
    st.switch_page("app.py")
    st.stop()

current_user = st.session_state["user_data"]
is_admin = current_user.get("is_admin", False)
allowed_ids = [int(i) for i in (current_user.get("allowed_projects") or [])]

# --- 3. SIDEBAR & CONTESTO PROGETTO ---
st.sidebar.title("🏗️ BIM Manager")
st.sidebar.write(f"👤 **{current_user['email']}**")
if st.sidebar.button("🚪 Logout"):
    st.session_state["user_data"] = None
    st.switch_page("app.py")

# Recupero Progetti per definire project_id
query = supabase.table("projects").select("*").order("project_code")
if not is_admin:
    query = query.in_("id", allowed_ids if allowed_ids else [0])
projects_list = query.execute().data

# --- LOGICA PERSISTENZA PROGETTO ---
if "selected_project_id" not in st.session_state:
    st.session_state["selected_project_id"] = None

project_id = None
if projects_list:
    project_options = {f"{p['project_code']} - {p['project_name']}": p['id'] for p in projects_list}
    project_labels = list(project_options.keys())
    
    # Trova l'indice del progetto precedentemente selezionato
    default_index = 0
    if st.session_state["selected_project_id"]:
        for i, p_id in enumerate(project_options.values()):
            if p_id == st.session_state["selected_project_id"]:
                default_index = i
                break
    
    selected_label = st.selectbox(
        "Current Project Context:", 
        project_labels, 
        index=default_index,
        key="project_selector"
    )
    project_id = project_options[selected_label]
    st.session_state["selected_project_id"] = project_id
else:
    st.info("Nessun progetto assegnato.")
    st.stop()

# --- 4. RECUPERO PARAMETRI MAPPATI ---
maps_resp = supabase.table("parameter_mappings").select("db_column_name").eq("project_id", project_id).execute()
mapped_params = [m['db_column_name'] for m in maps_resp.data]

# --- 5. LOGICA PAGINA: ROOMS MANAGEMENT ---
st.header("📍 Rooms Management")

# --- IMPORT / EXPORT ---
with st.expander("📥 Import / Export Rooms"):
    c1, c2 = st.columns(2)
    with c1:
        st.write("**Export Rooms**")
        rooms_raw = supabase.table("rooms").select("*").eq("project_id", project_id).order("room_number").execute().data
        if rooms_raw:
            df_exp = pd.DataFrame([{
                "Number": r["room_number"], 
                "Name": r["room_name_planned"], 
                "Area": r.get("area"),
                **(r.get("parameters") or {})
            } for r in rooms_raw])
            buf = io.BytesIO()
            with pd.ExcelWriter(buf, engine='xlsxwriter') as writer: 
                df_exp.to_excel(writer, index=False)
            st.download_button(
                "⬇️ Download Excel", 
                data=buf.getvalue(), 
                file_name=f"rooms_proj_{project_id}.xlsx"
            )
        else:
            st.info("Nessuna stanza trovata.")
        
        # Template vuoto sempre disponibile
        st.write("---")
        st.write("**Download Template Vuoto**")
        template_columns = ["Number", "Name", "Area"] + mapped_params
        df_template = pd.DataFrame(columns=template_columns)
        buf_template = io.BytesIO()
        with pd.ExcelWriter(buf_template, engine='xlsxwriter') as writer:
            df_template.to_excel(writer, index=False)
        st.download_button(
            "📄 Download Template", 
            data=buf_template.getvalue(), 
            file_name=f"rooms_template_proj_{project_id}.xlsx",
            help="Scarica un file Excel vuoto con le colonne corrette da compilare"
        )

    with c2:
        st.write("**Import Rooms**")
        up_file = st.file_uploader("Upload Rooms XLSX", type=["xlsx"])
        if up_file and st.button("🚀 Upload & Sync"):
            df_up = pd.read_excel(up_file, dtype=str)
            bulk_data = []
            for _, row in df_up.iterrows():
                # Prendiamo il numero stanza (obbligatorio)
                num = str(row.get("Number", "")).strip() if pd.notna(row.get("Number")) else None
                
                if num:
                    # Pulizia parametri dinamici (evitiamo NaN)
                    p_dict = {}
                    for p in mapped_params:
                        if p in row and pd.notna(row[p]):
                            p_dict[p] = str(row[p]).strip()
                    
                    # Preparazione riga
                    room_entry = {
                        "project_id": project_id, 
                        "room_number": num,
                        "room_name_planned": str(row.get("Name", "")).strip() if pd.notna(row.get("Name")) else "",
                        "parameters": p_dict, 
                        "is_synced": False
                    }
                    
                    # Gestione Area (solo se valida)
                    area_val = row.get("Area")
                    if pd.notna(area_val):
                        try:
                            room_entry["area"] = float(area_val)
                        except:
                            room_entry["area"] = None
                    else:
                        room_entry["area"] = None
                        
                    bulk_data.append(room_entry)
            
            if bulk_data:
                try:
                    supabase.table("rooms").upsert(bulk_data, on_conflict="project_id,room_number").execute()
                    st.success(f"Sincronizzate {len(bulk_data)} stanze!")
                    st.rerun()
                except Exception as e:
                    st.error(f"Errore durante l'upload: {str(e)}")
                    st.info("💡 Verifica che nel database esista un indice UNIQUE su 'project_id' e 'room_number'.")

# --- AGGIUNTA SINGOLA ---
st.divider()
with st.form("new_room_form"):
    st.subheader("➕ Add Single Room")
    c1, c2 = st.columns(2)
    room_num = c1.text_input("Room Number*", placeholder="es: 101")
    room_name = c2.text_input("Room Name", placeholder="es: Ufficio")
    
    if st.form_submit_button("💾 Save Room", use_container_width=True):
        if room_num:
            new_room = {
                "project_id": project_id,
                "room_number": room_num.strip(),
                "room_name_planned": room_name.strip() if room_name else "",
                "area": None,
                "parameters": {},
                "is_synced": False
            }
            try:
                supabase.table("rooms").insert(new_room).execute()
                st.success(f"Stanza {room_num} aggiunta!")
                st.rerun()
            except Exception as e:
                st.error(f"Errore: {str(e)}")
        else:
            st.warning("Il numero della stanza è obbligatorio!")

# --- TABELLA GESTIONE ---
st.divider()
st.subheader("📋 Current Rooms")

# Legenda stati
st.info("💡 **Status**: ✅ Sincronizzato | ⚠️ Modificato Web | ❗ Non in Revit | ❌ Mai Sincronizzato")

search_q = st.text_input("🔍 Filtra locali", placeholder="Cerca numero o nome...")
rooms_resp = supabase.table("rooms").select("*").eq("project_id", project_id).order("room_number").execute()

if rooms_resp.data:
    flat_data = []
    for r in rooms_resp.data:
        # Logica icone 4 stati
        is_synced = r.get("is_synced")
        last_sync = r.get("last_sync_at")
        
        if is_synced is True: 
            status_icon = "✅"
        elif is_synced is False and last_sync: 
            status_icon = "⚠️"
        elif is_synced is None and last_sync: 
            status_icon = "❗"
        else: 
            status_icon = "❌"
            
        sync_str = pd.to_datetime(last_sync).strftime('%d/%m/%Y %H:%M') if last_sync else "Mai"
        
        row = {
            "id": int(r["id"]), 
            "Status": status_icon, 
            "Number": r["room_number"], 
            "Name": r["room_name_planned"], 
            "Area (m²)": float(r.get("area") or 0), 
            "Last_Sync": sync_str
        }
        
        # Aggiungi parametri mappati
        p_json = r.get("parameters") or {}
        for p in mapped_params: 
            row[p] = p_json.get(p, "")
        
        flat_data.append(row)
    
    df_display = pd.DataFrame(flat_data)
    
    # Filtro ricerca
    if search_q:
        mask = df_display.apply(lambda x: x.astype(str).str.contains(search_q, case=False).any(), axis=1)
        df_display = df_display[mask].copy()

    df_display.insert(0, "Select", False)

    # Data Editor
    updated_df = st.data_editor(
        df_display, 
        use_container_width=True, 
        hide_index=True,
        column_config={
            "id": None, 
            "Select": st.column_config.CheckboxColumn("Elimina", default=False),
            "Status": st.column_config.TextColumn("Sync", width="small"),
            "Number": st.column_config.TextColumn("Room Number"),
            "Name": st.column_config.TextColumn("Room Name"),
            "Area (m²)": st.column_config.NumberColumn("📐 Area", format="%.2f m²"),
            "Last_Sync": st.column_config.TextColumn("Data Sync", disabled=True)
        },
        key="rooms_editor_v4"
    )

    # Pulsanti azione
    col_save, col_delete = st.columns(2)
    
    with col_save:
        if st.button("💾 SAVE ALL CHANGES", type="primary", use_container_width=True):
            success_count = 0
            for i in range(len(updated_df)):
                row_new = updated_df.iloc[i]
                row_old = df_display.iloc[i]
                
                # Confronta parametri
                new_p = {p: row_new[p] for p in mapped_params if p in row_new}
                old_p = {p: row_old[p] for p in mapped_params if p in row_old}
                
                # Verifica se ci sono modifiche
                if (row_new["Name"] != row_old["Name"]) or \
                   (row_new["Area (m²)"] != row_old["Area (m²)"]) or \
                   (new_p != old_p):
                    supabase.table("rooms").update({
                        "room_name_planned": row_new["Name"], 
                        "area": float(row_new["Area (m²)"]) if row_new["Area (m²)"] > 0 else None,
                        "parameters": new_p,
                        "is_synced": False  # Reset per forzare handshake Revit
                    }).eq("id", int(row_new["id"])).execute()
                    success_count += 1
            
            if success_count > 0:
                st.success(f"Aggiornate {success_count} stanze.")
                st.rerun()
            else:
                st.info("Nessuna modifica rilevata.")
    
    with col_delete:
        if st.button("🗑️ DELETE SELECTED", use_container_width=True):
            ids_to_del = [int(i) for i in updated_df[updated_df["Select"] == True]["id"].tolist()]
            if ids_to_del:
                supabase.table("rooms").delete().in_("id", ids_to_del).execute()
                st.success(f"Eliminate {len(ids_to_del)} stanze.")
                st.rerun()
            else:
                st.warning("Nessuna stanza selezionata per l'eliminazione.")
else:
    st.info("Usa il form sopra o l'import Excel per aggiungere delle stanze.")
