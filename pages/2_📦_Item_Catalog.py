import streamlit as st
import pandas as pd
from supabase import create_client, Client
import io

# --- 1. CONFIGURAZIONE E CONNESSIONE ---
# Recupero credenziali dai secrets
try:
    url = st.secrets["SUPABASE_URL"]
    key = st.secrets["SUPABASE_KEY"]
except KeyError:
    st.error("Configurazione mancante nei Secrets! (SUPABASE_URL, SUPABASE_KEY)")
    st.stop()

@st.cache_resource
def get_supabase_client() -> Client:
    return create_client(url, key)

supabase = get_supabase_client()

# --- 2. CONTROLLO ACCESSO ---
if "user_data" not in st.session_state or st.session_state["user_data"] is None:
    st.warning("⚠️ Accesso non autorizzato. Torna alla Home per effettuare il login.")
    if st.button("Vai alla Login"):
        st.switch_page("app.py")
    st.stop()

current_user = st.session_state["user_data"]
is_admin = current_user.get("is_admin", False)
allowed_ids = [int(i) for i in (current_user.get("allowed_projects") or [])]

# --- 3. SIDEBAR CONDIVISA ---
st.sidebar.title("🏗️ BIM Manager")
st.sidebar.write(f"👤 **{current_user['email']}**")
if st.sidebar.button("🚪 Logout"):
    st.session_state["user_data"] = None
    st.switch_page("app.py")

# --- LOGICA PERSISTENZA PROGETTO ---
if "selected_project_id" not in st.session_state:
    st.session_state["selected_project_id"] = None

# --- 4. SELEZIONE PROGETTO (Contesto Globale) ---
query = supabase.table("projects").select("*").order("project_code")
if not is_admin:
    query = query.in_("id", allowed_ids if allowed_ids else [0])
projects_list = query.execute().data

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
        key="project_selector_catalog"
    )
    project_id = project_options[selected_label]
    st.session_state["selected_project_id"] = project_id
else:
    st.info("Nessun progetto assegnato.")
    st.stop()

# --- 5. LOGICA PAGINA: ITEM CATALOG ---
st.header("📦 Item Catalog Management")

# --- SEZIONE IMPORT / EXPORT EXCEL ---
with st.expander("📥 Import / Export Catalog Items"):
    c1, c2 = st.columns(2)
    with c1:
        st.write("**Export Catalog**")
        items_raw = supabase.table("items").select("*").eq("project_id", project_id).execute()
        if items_raw.data:
            df_item_exp = pd.DataFrame(items_raw.data)[["item_code", "item_description"]]
            buf = io.BytesIO()
            with pd.ExcelWriter(buf, engine='xlsxwriter') as writer: 
                df_item_exp.to_excel(writer, index=False)
            st.download_button("⬇️ Download Item Catalog", data=buf.getvalue(), file_name=f"catalog_proj_{project_id}.xlsx")
        else:
            st.info("Catalog is empty.")
    
    with c2:
        st.write("**Import/Sync Catalog**")
        up_item_file = st.file_uploader("Upload Item XLSX", type=["xlsx"], key="up_items")
        if up_item_file and st.button("🚀 Sync Catalog"):
            df_item_up = pd.read_excel(up_item_file, dtype=str)
            item_bulk = []
            for _, row in df_item_up.iterrows():
                if pd.notna(row.get("item_code")):
                    item_bulk.append({
                        "project_id": project_id,
                        "item_code": str(row["item_code"]).strip(),
                        "item_description": str(row.get("item_description", ""))
                    })
            
            if item_bulk:
                try:
                    supabase.table("items").upsert(item_bulk, on_conflict="project_id,item_code").execute()
                    st.success(f"Successfully synced {len(item_bulk)} items!")
                    st.rerun()
                except Exception as e:
                    st.error(f"Errore durante l'upsert: {e}")
            else:
                st.error("No valid data found in file.")

# --- AGGIUNTA SINGOLA ---
with st.expander("➕ Add New Item Manually"):
    with st.form("ni"):
        c1, c2 = st.columns(2)
        ic, ides = c1.text_input("Code"), c2.text_input("Description")
        if st.form_submit_button("Save Item"):
            if ic: 
                supabase.table("items").insert({
                    "project_id": project_id, 
                    "item_code": ic, 
                    "item_description": ides
                }).execute()
                st.success("Item aggiunto!")
                st.rerun()

# --- TABELLA E FILTRI ---
st.divider()
si = st.text_input("🔍 Filter Items Table", placeholder="Cerca codice o descrizione...")
items = supabase.table("items").select("*").eq("project_id", project_id).execute().data

if items:
    df_i = pd.DataFrame(items).drop(columns=['project_id'])
    if si: 
        df_i = df_i[df_i.apply(lambda x: x.astype(str).str.contains(si, case=False).any(), axis=1)]
    
    df_i.insert(0, "Select", False)
    
    # Editor dati per cancellazione o modifica rapida
    ed_i = st.data_editor(
        df_i, 
        use_container_width=True, 
        hide_index=True, 
        column_config={
            "id": None, # Nasconde l'ID interno
            "Select": st.column_config.CheckboxColumn("Seleziona", default=False)
        }
    )
    
    if st.button("🗑️ Delete Selected Items", type="secondary"):
        ids_to_delete = [int(i) for i in ed_i[ed_i["Select"] == True]["id"].tolist()]
        if ids_to_delete:
            supabase.table("items").delete().in_("id", ids_to_delete).execute()
            st.success(f"Eliminati {len(ids_to_delete)} elementi.")
            st.rerun()
else:
    st.info("Nessun elemento presente nel catalogo per questo progetto.")
