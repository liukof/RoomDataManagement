import streamlit as st
import pandas as pd
from supabase import create_client, Client
import io

# --- SETUP SUPABASE ---
try:
    url = st.secrets["SUPABASE_URL"]
    key = st.secrets["SUPABASE_KEY"]
except:
    st.error("Configurazione mancante nei Secrets!")
    st.stop()

supabase: Client = create_client(url, key)

st.set_page_config(page_title="BIM Data Manager PRO", layout="wide", page_icon="🏗️")

# --- RECUPERO PROGETTI ---
try:
    projects_resp = supabase.table("projects").select("*").order("project_code").execute()
    projects_list = projects_resp.data
except Exception as e:
    st.error(f"Errore di connessione: {e}")
    st.stop()

# --- BARRA DI NAVIGAZIONE ---
st.sidebar.title("🧭 Menu")
menu = st.sidebar.radio("Vai a:", ["Locali", "Mappatura Parametri", "Gestione Progetti"])

# --- LOGICA COMUNE PER PROGETTI ---
if menu in ["Locali", "Mappatura Parametri"]:
    if not projects_list:
        st.sidebar.warning("Crea prima un progetto in 'Gestione Progetti'.")
        st.stop()

    st.sidebar.divider()
    project_options = {f"{p['project_code']} - {p['project_name']}": p for p in projects_list}
    selected_label = st.sidebar.selectbox("Progetto attivo:", list(project_options.keys()))
    project_id = project_options[selected_label]['id']

    st.title(f"{'📍' if menu == 'Locali' else '🔗'} {menu}")
    st.caption(f"Commessa: **{selected_label}**")

    # --- 1. PAGINA: LOCALI (EDITOR JSONB + AGGIUNTA) ---
    if menu == "Locali":
        # Sidebar per aggiunta locale
        with st.sidebar.expander("➕ Aggiungi Locale"):
            with st.form(key="form_new_room", clear_on_submit=True):
                new_num = st.text_input("Numero Locale")
                new_nam = st.text_input("Nome Programmato")
                if st.form_submit_button("Salva Locale"):
                    if new_num and new_nam:
                        supabase.table("rooms").insert({
                            "room_number": new_num,
                            "room_name_planned": new_nam,
                            "project_id": project_id,
                            "parameters": {}
                        }).execute()
                        st.rerun()

        # Recupero mappature e dati
        maps_resp = supabase.table("parameter_mappings").select("db_column_name").eq("project_id", project_id).execute()
        mapped_params = [m['db_column_name'] for m in maps_resp.data]
        rooms_resp = supabase.table("rooms").select("*").eq("project_id", project_id).order("room_number").execute()
        
        if rooms_resp.data:
            flat_data = []
            for r in rooms_resp.data:
                row = {"id": r["id"], "room_number": r["room_number"], "room_name_planned": r["room_name_planned"]}
                params_json = r.get("parameters") or {}
                for p in mapped_params:
                    row[p] = params_json.get(p, "")
                flat_data.append(row)

            df_rooms = pd.DataFrame(flat_data)
            st.subheader("📝 Editor Dati")
            edited_df = st.data_editor(
                df_rooms,
                column_config={"id": None, "room_number": st.column_config.TextColumn("Numero", disabled=True)},
                use_container_width=True, hide_index=True, key="editor_locali"
            )

            if st.button("💾 Salva Modifiche"):
                try:
                    for _, row in edited_df.iterrows():
                        updated_params = {p: row[p] for p in mapped_params if p in row}
                        supabase.table("rooms").update({
                            "room_name_planned": row["room_name_planned"],
                            "parameters": updated_params
                        }).eq("id", row["id"]).execute()
                    st.success("Modifiche salvate!")
                    st.rerun()
                except Exception as e:
                    st.error(f"Errore: {e}")
        else:
            st.info("Nessun locale trovato per questo progetto.")

    # --- 2. PAGINA: MAPPATURA PARAMETRI ---
    elif menu == "Mappatura Parametri":
        with st.expander("📥 Importazione Massiva"):
            template_df = pd.DataFrame(columns=["Database", "Revit"])
            buffer = io.BytesIO()
            with pd.ExcelWriter(buffer, engine='xlsxwriter') as writer:
                template_df.to_excel(writer, index=False)
            st.download_button("⬇️ Scarica Template", data=buffer.getvalue(), file_name="template.xlsx")
            
            up_file = st.file_uploader("Carica file", type=["xlsx", "csv"])
            if up_file and st.button("🚀 Conferma Import"):
                df_up = pd.read_excel(up_file) if up_file.name.endswith('.xlsx') else pd.read_csv(up_file)
                batch = [{"project_id": project_id, "db_column_name": str(r['Database']).strip(), "revit_parameter_name": str(r['Revit']).strip()} for _, r in df_up.dropna().iterrows()]
                supabase.table("parameter_mappings").insert(batch).execute()
                st.rerun()

        st.subheader("➕ Aggiungi Mappatura")
        with st.form("single_map"):
            c1, c2 = st.columns(2)
            db_c = c1.text_input("Chiave nel Database")
            rev_p = c2.text_input("Nome Parametro Revit")
            if st.form_submit_button("Salva"):
                supabase.table("parameter_mappings").insert({"project_id": project_id, "db_column_name": db_c, "revit_parameter_name": rev_p}).execute()
                st.rerun()

        st.subheader("📋 Mappature Attive")
        res_map = supabase.table("parameter_mappings").select("*").eq("project_id", project_id).execute()
        if res_map.data:
            st.dataframe(pd.DataFrame(res_map.data)[["db_column_name", "revit_parameter_name"]], use_container_width=True, hide_index=True)
            if st.button("🗑️ Reset Mappature"):
                supabase.table("parameter_mappings").delete().eq("project_id", project_id).execute()
                st.rerun()

# --- 3. PAGINA: GESTIONE PROGETTI (RIPRISTINATA) ---
elif menu == "Gestione Progetti":
    st.title("⚙️ Gestione Progetti")
    
    t1, t2 = st.tabs(["➕ Nuovo Progetto", "📝 Modifica / Elimina"])

    with t1:
        with st.form("new_prj_form", clear_on_submit=True):
            st.subheader("Crea Progetto")
            new_cp = st.text_input("Codice Progetto")
            new_np = st.text_input("Nome Progetto")
            if st.form_submit_button("Crea"):
                if new_cp and new_np:
                    supabase.table("projects").insert({"project_code": new_cp, "project_name": new_np}).execute()
                    st.success("Progetto creato!")
                    st.rerun()

    with t2:
        if projects_list:
            proj_to_manage = st.selectbox("Seleziona Progetto:", {f"{p['project_code']} - {p['project_name']}": p for p in projects_list}.keys())
            target_prj = {f"{p['project_code']} - {p['project_name']}": p for p in projects_list}[proj_to_manage]
            
            st.subheader("Modifica Dati")
            edit_c = st.text_input("Modifica Codice", value=target_prj['project_code'])
            edit_n = st.text_input("Modifica Nome", value=target_prj['project_name'])
            
            c_save, c_del = st.columns(2)
            if c_save.button("💾 Salva Modifiche"):
                supabase.table("projects").update({"project_code": edit_c, "project_name": edit_n}).eq("id", target_prj['id']).execute()
                st.success("Progetto aggiornato!")
                st.rerun()
            
            st.divider()
            st.subheader("🔥 Zona Pericolo")
            del_confirm = st.text_input("Scrivi 'ELIMINA' per confermare la cancellazione totale del progetto")
            if c_del.button("Elimina Progetto"):
                if del_confirm == "ELIMINA":
                    supabase.table("projects").delete().eq("id", target_prj['id']).execute()
                    st.success("Progetto eliminato.")
                    st.rerun()
                else:
                    st.error("Conferma necessaria.")
        else:
            st.info("Nessun progetto disponibile.")
