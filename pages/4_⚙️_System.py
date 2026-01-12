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
with t2:
    st.subheader("Authorize New User")
    with st.form("new_user_form"):
        c1, c2 = st.columns([2, 1])
        new_email = c1.text_input("User Email").lower().strip()
        is_new_admin = c2.checkbox("Grant Admin Privileges")
        if st.form_submit_button("➕ Authorize User", use_container_width=True):
            if "@" in new_email:
                supabase.table("user_permissions").insert({
                    "email": new_email, 
                    "is_admin": is_new_admin
                }).execute()
                st.success(f"User {new_email} authorized.")
                st.rerun()
            else: st.error("Invalid email address.")

    st.divider()
    
    # Recupero dati progetti e utenti
    all_projects = supabase.table("projects").select("*").order("project_code").execute().data
    users = supabase.table("user_permissions").select("*").execute().data

    if users and all_projects:
        st.subheader("Project Assignment")
        p_map = {f"{p['project_code']}": int(p['id']) for p in all_projects}
        p_inv_map = {int(p['id']): f"{p['project_code']}" for p in all_projects}
        
        u_to_ed = st.selectbox("Select User to edit permissions:", [u['email'] for u in users], key="sel_u_perm")
        curr_u = next(u for u in users if u['email'] == u_to_ed)
        
        curr_ids = [int(x) for x in (curr_u.get("allowed_projects") or [])]
        curr_labels = [p_inv_map[pid] for pid in curr_ids if pid in p_inv_map]
        
        sel_p = st.multiselect("Allowed Projects for this user:", list(p_map.keys()), default=curr_labels)
        
        if st.button("💾 Update User Permissions", use_container_width=True):
            new_ids = [int(p_map[p]) for p in sel_p]
            supabase.table("user_permissions").update({"allowed_projects": new_ids}).eq("email", u_to_ed).execute()
            st.success(f"Permissions updated for {u_to_ed}!")
            st.rerun()
            
    st.divider()
    st.subheader("🗑️ Account Management")
    if users:
        st.write("Seleziona gli account da rimuovere dal sistema:")
        df_u = pd.DataFrame(users)[["email", "is_admin"]]
        df_u.insert(0, "Select", False)
        
        ed_u = st.data_editor(
            df_u, 
            use_container_width=True, 
            hide_index=True,
            column_config={
                "Select": st.column_config.CheckboxColumn("Elimina", default=False),
                "email": st.column_config.TextColumn("User Email", disabled=True),
                "is_admin": st.column_config.CheckboxColumn("Admin", disabled=True)
            }
        )
        
        if st.button("❌ DELETE SELECTED ACCOUNTS", type="primary", use_container_width=True):
            emails_to_del = ed_u[ed_u["Select"] == True]["email"].tolist()
            if emails_to_del:
                # Protezione: non eliminare se stessi (opzionale ma consigliato)
                if user['email'] in emails_to_del:
                    st.error("Non puoi eliminare il tuo stesso account mentre sei loggato.")
                else:
                    supabase.table("user_permissions").delete().in_("email", emails_to_del).execute()
                    st.success(f"Rimosso l'accesso per {len(emails_to_del)} utenti.")
                    st.rerun()
            else:
                st.warning("Seleziona almeno un account.")
# --- TAB 2: PERMESSI UTENTE ---
with t2:
    st.subheader("Authorize New User")
    with st.form("new_user_form"):
        new_email = st.text_input("User Email").lower().strip()
        is_new_admin = st.checkbox("Grant Admin Privileges")
        if st.form_submit_button("➕ Authorize User"):
            if "@" in new_email:
                supabase.table("user_permissions").insert({
                    "email": new_email, 
                    "is_admin": is_new_admin
                }).execute()
                st.success(f"User {new_email} authorized.")
                st.rerun()
            else:
                st.error("Invalid email address.")

    st.divider()
    st.subheader("Project Assignment")
    users = supabase.table("user_permissions").select("*").execute().data
    
    if users and all_projects:
        # Mappa nomi progetti -> ID
        p_map = {f"{p['project_code']}": int(p['id']) for p in all_projects}
        p_inv_map = {int(p['id']): f"{p['project_code']}" for p in all_projects}
        
        u_to_ed = st.selectbox("Select User to edit permissions:", [u['email'] for u in users])
        curr_u = next(u for u in users if u['email'] == u_to_ed)
        
        # Recupera ID correnti e converti in label per il multiselect
        curr_ids = [int(x) for x in (curr_u.get("allowed_projects") or [])]
        curr_labels = [p_inv_map[pid] for pid in curr_ids if pid in p_inv_map]
        
        sel_p = st.multiselect("Allowed Projects for this user:", list(p_map.keys()), default=curr_labels)
        
        if st.button("💾 Update User Permissions", use_container_width=True):
            new_ids = [int(p_map[p]) for p in sel_p]
            supabase.table("user_permissions").update({
                "allowed_projects": new_ids
            }).eq("email", u_to_ed).execute()
            st.success(f"Permissions updated for {u_to_ed}!")
            st.rerun()
            
    st.divider()
    st.subheader("Users List")
    if users:
        df_u = pd.DataFrame(users)[["email", "is_admin", "allowed_projects"]]
        df_u.insert(0, "Select", False)
        ed_u = st.data_editor(df_u, use_container_width=True, hide_index=True)
        
        if st.button("🗑️ Revoke Access for Selected Users"):
            emails_to_del = ed_u[ed_u["Select"] == True]["email"].tolist()
            if emails_to_del:
                supabase.table("user_permissions").delete().in_("email", emails_to_del).execute()
                st.rerun()

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
