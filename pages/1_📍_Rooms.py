import streamlit as st
import pandas as pd
from supabase import create_client, Client
import io

# --- 1. SETUP & CONNESSIONE ---
try:
    url = st.secrets["SUPABASE_URL"]
    key = st.secrets["SUPABASE_KEY"]
except KeyError:
    st.error("Configurazione mancante nei Secrets!")
    st.stop()

@st.cache_resource(ttl=3600)
def get_supabase_client() -> Client:
    return create_client(url, key)

supabase = get_supabase_client()

# --- 2. CONTROLLO ACCESSO ---
if "user_data" not in st.session_state or st.session_state["user_data"] is None:
    st.switch_page("app.py")
    st.stop()

current_user = st.session_state["user_data"]
is_admin = current_user.get("is_admin", False)
allowed_ids = [int(i) for i in (current_user.get("allowed_projects") or [])]

# --- 3. SIDEBAR & PROGETTO ---
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
    st.error("Nessun progetto assegnato.")
    st.stop()

project_options = {f"{p['project_code']} - {p['project_name']}": p for p in projects_list}
selected_label = st.selectbox("Current Project Context:", list(project_options.keys()))
project_id = int(project_options[selected_label]['id'])

st.header("📍 Rooms & Item Lists")

# --- 4. MAPPING PARAMETRI ---
maps_resp = supabase.table("parameter_mappings").select("db_column_name").eq("project_id", project_id).execute()
mapped_params = [m['db_column_name'] for m in maps_resp.data]

# --- 5. GESTIONE IMPORT / EXPORT (OMESSA PER BREVITÀ, MANTIENI QUELLA ESISTENTE) ---
# ... (Mantenere qui il blocco expander 📥 Manage Rooms già funzionante)

# --- 6. TABELLA EDITABILE CON LOGICA DI SALVATAGGIO ROBUSTA ---
st.divider()
search_q = st.text_input("🔍 Filter (Number or Name)", placeholder="Cerca...")

# Fetch dei dati dal DB
rooms_resp = supabase.table("rooms").select("*").eq("project_id", project_id).order("room_number").execute()

if rooms_resp.data:
    flat_data = []
    for r in rooms_resp.data:
        row = {"id": int(r["id"]), "Number": r["room_number"], "Name": r["room_name_planned"], "Area (mq)": float(r.get("area") or 0)}
        p_json = r.get("parameters") or {}
        for p in mapped_params: row[p] = p_json.get(p, "")
        flat_data.append(row)
    
    df_base = pd.DataFrame(flat_data)
    
    if search_q:
        mask = df_base.apply(lambda x: x.astype(str).str.contains(search_q, case=False).any(), axis=1)
        df_display = df_base[mask].copy()
    else:
        df_display = df_base.copy()
    
    df_display.insert(0, "Select", False)

    st.subheader(f"📍 Rooms List ({len(df_display)})")
    st.caption("💡 Ricorda: premi **Invio** o clicca fuori dalla cella per confermare la modifica prima di salvare.")

    # Usiamo st.data_editor con una chiave specifica
    # I cambiamenti vengono salvati in st.session_state["rooms_editor_key"]
    edited_data = st.data_editor(
        df_display,
        use_container_width=True,
        hide_index=True,
        column_config={
            "id": None, 
            "Number": st.column_config.TextColumn("Room Number", disabled=True),
            "Area (mq)": st.column_config.NumberColumn("📐 Area (mq)", format="%.2f m²", disabled=True),
            "Select": st.column_config.CheckboxColumn("Select", default=False)
        },
        key="rooms_editor_key"
    )

    # --- BOTTONI AZIONE ---
    col_save, col_del = st.columns([1, 1])

    with col_save:
        # Il salvataggio ora è basato sul dataframe 'edited_data' restituito dall'editor
        if st.button("💾 SAVE ALL CHANGES", type="primary", use_container_width=True):
            success_count = 0
            
            # Recuperiamo i dati che Streamlit ha effettivamente recepito
            for i in range(len(edited_data)):
                row_new = edited_data.iloc[i]
                row_old = df_display.iloc[i]
                
                # Ricostruzione parametri JSON
                new_params = {p: row_new[p] for p in mapped_params}
                old_params = {p: row_old[p] for p in mapped_params}
                
                # Verifica cambiamenti (Nome o Parametri JSON)
                if (row_new["Name"] != row_old["Name"]) or (new_params != old_params):
                    try:
                        supabase.table("rooms").update({
                            "room_name_planned": str(row_new["Name"]),
                            "parameters": new_params
                        }).eq("id", int(row_new["id"])).execute()
                        success_count += 1
                    except Exception as e:
                        st.error(f"Errore sull'ID {row_new['id']}: {e}")
            
            if success_count > 0:
                st.success(f"✅ {success_count} locali aggiornati correttamente!")
                st.rerun()
            else:
                st.info("Nessuna modifica rilevata. Assicurati di aver premuto **Invio** nelle celle modificate.")

    with col_del:
        if st.button("🗑️ DELETE SELECTED", use_container_width=True):
            ids_to_del = edited_data[edited_data["Select"] == True]["id"].tolist()
            if ids_to_del:
                supabase.table("rooms").delete().in_("id", ids_to_del).execute()
                st.rerun()

# --- 7. ASSEGNAZIONE MASSIVA ITEM (MANTIENI QUELLA ESISTENTE) ---
# ... (Mantenere qui il blocco 📦 Bulk Item Assignment già funzionante)
st.divider()
st.subheader("📦 Bulk Item Assignment")
catalog = supabase.table("items").select("*").eq("project_id", project_id).execute().data
if catalog:
    item_opt = {f"{i['item_code']} - {i['item_description']}": int(i['id']) for i in catalog}
    with st.form("bulk_item"):
        c1, c2 = st.columns([3, 1])
        t_item = c1.selectbox("Seleziona Item:", list(item_opt.keys()))
        t_qty = c2.number_input("Quantità", min_value=1, value=1)
        if st.form_submit_button("🚀 Assign to Filtered Set"):
            # Usiamo gli ID del dataframe visualizzato (rispetta i filtri di ricerca)
            bulk = [{"room_id": int(rid), "item_id": item_opt[t_item], "quantity": int(t_qty)} for rid in df_display['id'].tolist()]
            supabase.table("room_items").insert(bulk).execute()
            st.success("Assegnazione completata!"); st.rerun()
