import streamlit as st
import pandas as pd
from supabase import create_client, Client

# --- SETUP & AUTH ---
try:
    url = st.secrets["SUPABASE_URL"]
    key = st.secrets["SUPABASE_KEY"]
except KeyError:
    st.error("Missing Configuration in Secrets!")
    st.stop()

@st.cache_resource
def get_supabase_client() -> Client:
    return create_client(url, key)

supabase = get_supabase_client()

# --- SECURITY CHECK (Solo Admin) ---
user = st.session_state.get("user_data")
if not user or not user.get("is_admin"):
    st.error("🛑 Accesso riservato agli amministratori.")
    if st.button("Torna alla Home"):
        st.switch_page("app.py")
    st.stop()

st.title("⚙️ System Management")
st.sidebar.title("🏗️ Admin Panel")
st.sidebar.write(f"👤 Admin: **{user['email']}**")

# --- DEFINIZIONE TAB ---
t1, t2, t3 = st.tabs(["🏗️ Projects Management", "👥 User Permissions", "✏️ Modify Projects"])

# --- TAB 1: CREAZIONE PROGETTI ---
with t1:
    st.subheader("Create New Project")
    with st.form("new_project_form"):
        c1, c2 = st.columns(2)
        pc = c1.text_input("Project Code", placeholder="e.g. PRJ-001")
        pn = c2.text_input("Project Name", placeholder="e.g. New Hospital Wing")
        if st.form_submit_button("🚀 Create Project", use_container_width=True):
            if pc and pn:
                try:
                    supabase.table("projects").insert({"project_code": pc, "project_name": pn}).execute()
                    st.success(f"Project {pc} created!")
                    st.rerun()
                except Exception as e:
                    st.error(f"Error: {e}")
            else:
                st.warning("Please fill all fields.")

# --- TAB 2: PERMESSI UTENTE ---
with t2:
    st.subheader("Authorize & Assign Projects")
    users = supabase.table("user_permissions").select("*").execute().data
    all_projects = supabase.table("projects").select("*").order("project_code").execute().data
    
    if users and all_projects:
        p_map = {f"{p['project_code']}": int(p['id']) for p in all_projects}
        p_inv_map = {int(p['id']): f"{p['project_code']}" for p in all_projects}
        
        u_to_ed = st.selectbox("Select User:", [u['email'] for u in users])
        curr_u = next(u for u in users if u['email'] == u_to_ed)
        
        curr_ids = [int(x) for x in (curr_u.get("allowed_projects") or [])]
        curr_labels = [p_inv_map[pid] for pid in curr_ids if pid in p_inv_map]
        
        sel_p = st.multiselect("Allowed Projects:", list(p_map.keys()), default=curr_labels)
        
        if st.button("💾 Update Permissions", use_container_width=True):
            new_ids = [int(p_map[p]) for p in sel_p]
            supabase.table("user_permissions").update({"allowed_projects": new_ids}).eq("email", u_to_ed).execute()
            st.success("Updated!"); st.rerun()

# --- TAB 3: MODIFY PROJECTS (NUOVA) ---
with t3:
    st.subheader("Edit Project Details")
    st.info("In questa sezione puoi modificare i codici e i nomi dei progetti esistenti.")
    
    # Ricarichiamo i progetti per avere i dati freschi
    projects_to_edit = supabase.table("projects").select("*").order("project_code").execute().data
    
    if projects_to_edit:
        df_edit = pd.DataFrame(projects_to_edit)[["id", "project_code", "project_name"]]
        
        # Usiamo data_editor per permettere la modifica diretta delle celle
        edited_df = st.data_editor(
            df_edit,
            column_config={
                "id": st.column_config.TextColumn("ID", disabled=True), # L'ID non deve essere toccato
                "project_code": st.column_config.TextColumn("Code", help="Modifica il codice progetto"),
                "project_name": st.column_config.TextColumn("Project Name", help="Modifica il nome")
            },
            hide_index=True,
            use_container_width=True,
            key="project_editor"
        )
        
        # Pulsante per salvare le modifiche rilevate nel data_editor
        if st.button("💾 Save Changes to Projects", type="primary", use_container_width=True):
            changes_made = 0
            for index, row in edited_df.iterrows():
                # Troviamo l'originale per vedere se è cambiato (ottimizzazione)
                original_row = next(p for p in projects_to_edit if p['id'] == row['id'])
                
                if row['project_code'] != original_row['project_code'] or row['project_name'] != original_row['project_name']:
                    supabase.table("projects").update({
                        "project_code": row['project_code'],
                        "project_name": row['project_name']
                    }).eq("id", row['id']).execute()
                    changes_made += 1
            
            if changes_made > 0:
                st.success(f"Aggiornati correttamente {changes_made} progetti.")
                st.rerun()
            else:
                st.info("Nessuna modifica rilevata.")

        st.divider()
        # Funzione di eliminazione spostata qui per pulizia
        st.subheader("🗑️ Danger Zone")
        df_del = df_edit.copy()
        df_del.insert(0, "Delete", False)
        to_del_table = st.data_editor(df_del, hide_index=True, use_container_width=True, column_config={"id":None})
        
        if st.button("Delete Selected Projects", type="secondary"):
            ids_to_del = [int(r['id']) for _, r in to_del_table[to_del_table["Delete"] == True].iterrows()]
            if ids_to_del:
                supabase.table("projects").delete().in_("id", ids_to_del).execute()
                st.success("Eliminati."); st.rerun()
    else:
        st.warning("Nessun progetto da modificare.")
