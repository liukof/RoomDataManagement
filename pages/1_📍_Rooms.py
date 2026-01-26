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
    st.warning("⚠️ Accesso non autorizzato. Torna alla Home per il login.")
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

query = supabase.table("projects").select("*").order("project_code")
if not is_admin:
    query = query.in_("id", allowed_ids if allowed_ids else [0])
projects_list = query.execute().data

if not projects_list:
    st.error("Nessun progetto assegnato a questo account.")
    st.stop()

project_options = {f"{p['project_code']} - {p['project_name']}": p for p in projects_list}
selected_label = st.selectbox("Current Project Context:", list(project_options.keys()))
project_id = int(project_options[selected_label]['id'])

st.header("📍 Rooms & Item Lists")

# --- 4. PARAMETER MAPPING CONTEXT ---
# Recuperiamo i nomi dei parametri definiti per questo progetto
maps_resp = supabase.table("parameter_mappings").select("db_column_name").eq("project_id", project_id).execute()
mapped_params = [m['db_column_name'] for m in maps_resp.data]

# --- 5. SECTION: IMPORT / EXPORT / MANUAL ADD ---
with st.expander("📥 Manage Rooms (Import / Export / Manual Add)"):
    tab_manual, tab_bulk = st.tabs(["➕ Add Single Room", "📁 Bulk Excel Sync"])
    
    with tab_manual:
        with st.form("single_room_form"):
            c1, c2 = st.columns(2)
            new_r_num = c1.text_input("Room Number (Unique)")
            new_r_name = c2.text_input("Room Name (Planned)")
            if st.form_submit_button("➕ Create Single Room", use_container_width=True):
                if new_r_num and new_r_name:
                    supabase.table("rooms").insert({
                        "project_id": project_id, 
                        "room_number": new_r_num.strip(), 
                        "room_name_planned": new_r_name.strip()
                    }).execute()
                    st.success(f"Room {new_r_num} added!"); st.rerun()
    
    with tab_bulk:
        c1, c2 = st.columns(2)
        with c1:
            st.write("**Export for Excel Edit**")
            rooms_raw = supabase.table("rooms").select("*").eq("project_id", project_id).order("room_number").execute()
            if rooms_raw.data:
                # Esportiamo Number, Name, Area e tutti i parametri dinamici mappati
                df_exp = pd.DataFrame([
                    {
                        "Number": r["room_number"], 
                        "Name": r["room_name_planned"], 
                        "Area (mq)": r.get("area", 0), 
                        **(r.get("parameters") or {})
                    } for r in rooms_raw.data
                ])
                buf = io.BytesIO()
                with pd.ExcelWriter(buf, engine='xlsxwriter') as writer:
                    df_exp.to_excel(writer, index=False)
                st.download_button("⬇️ Download Rooms Dataset", data=buf.getvalue(), file_name=f"rooms_{project_id}.xlsx", use_container_width=True)
        
        with c2:
            st.write("**Bulk Sync from Excel**")
            up_file = st.file_uploader("Upload XLSX", type=["xlsx"], key="rooms_up")
            if up_file and st.button("🚀 Start Bulk Sync", use_container_width=True):
                df_up = pd.read_excel(up_file, dtype=str)
                bulk_data = []
                for _, row in df_up.iterrows():
                    # Costruiamo il JSON dei parametri basandoci solo su quelli mappati
                    params_dict = {p: row[p] for p in mapped_params if p in row and pd.notna(row[p])}
                    bulk_data.append({
                        "project_id": project_id, 
                        "room_number": str(row["Number"]).strip(), 
                        "room_name_planned": str(row["Name"]), 
                        "parameters": params_dict
                    })
                if bulk_data:
                    supabase.table("rooms").upsert(bulk_data, on_conflict="project_id,room_number").execute()
                    st.success(f"Sincronizzati {len(bulk_data)} locali!"); st.rerun()

# --- 6. SECTION: ROOMS DATA EDITOR ---
st.divider()
search_q = st.text_input("🔍 Search Rooms", placeholder="Filter by number or name...")
rooms_resp = supabase.table("rooms").select("*").eq("project_id", project_id).order("room_number").execute()

if rooms_resp.data:
    # Appiattimento dati per la visualizzazione
    flat_data = []
    for r in rooms_resp.data:
        row = {
            "id": int(r["id"]), 
            "Number": r["room_number"], 
            "Name": r["room_name_planned"],
            "Area (mq)": float(r.get("area") or 0)
        }
        p_json = r.get("parameters") or {}
        for p in mapped_params:
            row[p] = p_json.get(p, "")
        flat_data.append(row)
    
    df_base = pd.DataFrame(flat_data)
    
    # Filtro ricerca
    if search_q:
        mask = df_base.apply(lambda x: x.astype(str).str.contains(search_q, case=False).any(), axis=1)
        df_filtered = df_base[mask].copy()
    else:
        df_filtered = df_base.copy()
    
    df_filtered.insert(0, "Select", False)

    st.subheader(f"📍 Project Rooms ({len(df_filtered)})")
    
    # Configurazione colonne Editor
    col_config = {
        "id": None, # Nascondi ID
        "Number": st.column_config.TextColumn("Room Number", disabled=True), # Bloccato per integrità
        "Area (mq)": st.column_config.NumberColumn("📐 Area (mq)", format="%.2f m²", disabled=True), # Solo da Revit
        "Select": st.column_config.CheckboxColumn("Select", default=False)
    }

    # Visualizzazione Tabella Editabile
    ed_rooms = st.data_editor(
        df_filtered, 
        use_container_width=True, 
        hide_index=True, 
        column_config=col_config,
        key="main_rooms_editor"
    )

    # --- BOTTONI AZIONE ---
    c_save, c_del_sel, c_del_all = st.columns([2, 1, 1])

    with c_save:
        if st.button("💾 SAVE PARAMETER CHANGES", type="primary", use_container_width=True):
            updated_count = 0
            # Confronto riga per riga tra df_filtered (originale) e ed_rooms (modificato)
            for idx in ed_rooms.index:
                row_new = ed_rooms.loc[idx]
                row_old = df_filtered.loc[idx]
                
                # Check se Nome o Parametri Mappati sono cambiati
                new_p = {p: row_new[p] for p in mapped_params}
                old_p = {p: row_old[p] for p in mapped_params}
                
                if new_p != old_p or row_new["Name"] != row_old["Name"]:
                    supabase.table("rooms").update({
                        "room_name_planned": row_new["Name"],
                        "parameters": new_p
                    }).eq("id", int(row_new["id"])).execute()
                    updated_count += 1
            
            if updated_count > 0:
                st.success(f"Aggiornati {updated_count} locali!"); st.rerun()
            else:
                st.info("Nessuna modifica rilevata.")

    with c_del_sel:
        if st.button("🗑️ DELETE SELECTED", use_container_width=True):
            ids_to_del = [int(i) for i in ed_rooms[ed_rooms["Select"] == True]["id"].tolist()]
            if ids_to_del:
                supabase.table("rooms").delete().in_("id", ids_to_del).execute()
                st.rerun()

    with c_del_all:
        if st.button("⚠️ DELETE ALL", type="secondary", use_container_width=True):
            if st.session_state.get('confirm_delete'): # Semplice doppio controllo
                supabase.table("rooms").delete().eq("project_id", project_id).execute()
                st.session_state['confirm_delete'] = False
                st.rerun()
            else:
                st.session_state['confirm_delete'] = True
                st.warning("Clicca di nuovo per confermare l'eliminazione TOTALE.")

# --- 7. SECTION: BULK ITEM ASSIGNMENT ---

st.divider()
st.subheader("📦 Bulk Item Assignment")
catalog = supabase.table("items").select("*").eq("project_id", project_id).execute().data

if catalog:
    item_opt = {f"{i['item_code']} - {i['item_description']}": int(i['id']) for i in catalog}
    with st.form("bulk_item_form"):
        col1, col2 = st.columns([3, 1])
        selected_item_label = col1.selectbox("Seleziona Item dal Catalogo:", list(item_opt.keys()))
        qty = col2.number_input("Quantità", min_value=1, value=1)
        
        st.write(f"ℹ️ L'item verrà aggiunto a tutti i **{len(df_filtered)}** locali attualmente visibili (filtrati).")
        
        if st.form_submit_button("🚀 Assign Item to Filtered Rooms", use_container_width=True):
            item_id = item_opt[selected_item_label]
            bulk_items = [
                {"room_id": int(rid), "item_id": item_id, "quantity": int(qty)} 
                for rid in df_filtered['id'].tolist()
            ]
            if bulk_items:
                supabase.table("room_items").insert(bulk_items).execute()
                st.success(f"Assegnati {len(bulk_items)} elementi con successo!"); st.rerun()
else:
    st.info("Il catalogo elementi è vuoto. Aggiungi prima degli item nella pagina 📦 Item Catalog.")
