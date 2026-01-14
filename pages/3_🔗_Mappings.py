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

project_id = None
if projects_list:
    project_options = {f"{p['project_code']} - {p['project_name']}": p for p in projects_list}
    selected_label = st.selectbox("Current Project Context:", list(project_options.keys()))
    project_id = int(project_options[selected_label]['id'])
else:
    st.info("Nessun progetto assegnato.")
    st.stop()

# --- 4. LOGICA PAGINA: PARAMETER MAPPING ---
st.header("🔗 Revit Parameter Mapping")

with st.expander("📥 Import / Export Mappings"):
    c1, c2 = st.columns(2)
    with c1:
        st.write("**Export Mappings**")
        maps = supabase.table("parameter_mappings").select("*").eq("project_id", project_id).execute().data
        if maps:
            df_m_exp = pd.DataFrame(maps)[["db_column_name", "revit_parameter_name"]]
            buf = io.BytesIO()
            with pd.ExcelWriter(buf, engine='xlsxwriter') as writer: 
                df_m_exp.to_excel(writer, index=False)
            st.download_button("⬇️ Download Excel", data=buf.getvalue(), file_name=f"mappings_proj_{project_id}.xlsx")
        else:
            st.info("Nessun mapping trovato.")

    with c2:
        st.write("**Import Mappings**")
        up_m = st.file_uploader("Upload Mappings XLSX", type=["xlsx"])
        if up_m and st.button("🚀 Upload & Sync"):
            df_m_up = pd.read_excel(up_m, dtype=str)
            m_bulk = []
            for _, row in df_m_up.iterrows():
                if pd.notna(row.get("db_column_name")) and pd.notna(row.get("revit_parameter_name")):
                    m_bulk.append({
                        "project_id": project_id, 
                        "db_column_name": str(row["db_column_name"]).strip(), 
                        "revit_parameter_name": str(row["revit_parameter_name"]).strip()
                    })
            
            if m_bulk:
                supabase.table("parameter_mappings").upsert(m_bulk, on_conflict="project_id,db_column_name").execute()
                st.success(f"Sincronizzati {len(m_bulk)} mapping!")
                st.rerun()

# --- AGGIUNTA SINGOLA ---
st.divider()
with st.form("new_mapping_form"):
    st.subheader("➕ Add Single Mapping")
    c1, c2 = st.columns(2)
    dbp = c1.text_input("Database Column Name", placeholder="es: finitura_pavimento")
    rvp = c2.text_input("Revit Parameter Name", placeholder="es: Revit_Floor_Finish")
    if st.form_submit_button("Save Mapping", use_container_width=True):
        if dbp and rvp:
            supabase.table("parameter_mappings").insert({
                "project_id": project_id, 
                "db_column_name": dbp.strip(), 
                "revit_parameter_name": rvp.strip()
            }).execute()
            st.rerun()

# --- TABELLA GESTIONE ---
st.divider()
st.subheader("📋 Current Mappings")
maps_data = supabase.table("parameter_mappings").select("*").eq("project_id", project_id).execute().data

if maps_data:
    df_m = pd.DataFrame(maps_data)[["id", "db_column_name", "revit_parameter_name"]]
    df_m.insert(0, "Select", False)
    
    ed_m = st.data_editor(
        df_m, 
        use_container_width=True, 
        hide_index=True, 
        column_config={
            "id": None,
            "Select": st.column_config.CheckboxColumn("Elimina", default=False)
        }
    )
    
    if st.button("🗑️ Delete Selected Mappings"):
        ids_to_del = [int(i) for i in ed_m[ed_m["Select"] == True]["id"].tolist()]
        if ids_to_del: 
            supabase.table("parameter_mappings").delete().in_("id", ids_to_del).execute()
            st.success(f"Eliminati {len(ids_to_del)} mapping.")
            st.rerun()
else:
    st.info("Usa il form sopra o l'import Excel per aggiungere dei mapping.")
