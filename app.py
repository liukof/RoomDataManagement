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

    # --- 1. PAGINA: LOCALI (EDITOR + IMPORT/EXPORT) ---
    if menu == "Locali":
        # Recupero mappature per colonne dinamiche
        maps_resp = supabase.table("parameter_mappings").select("db_column_name").eq("project_id", project_id).execute()
        mapped_params = [m['db_column_name'] for m in maps_resp.data]

        # SEZIONE IMPORT/EXPORT
        with st.expander("📥 Import / Export Locali (Excel)"):
            col_ex1, col_ex2 = st.columns(2)
            
            with col_ex1:
                st.write("**Esporta / Template**")
                # Prepariamo i dati per il download
                rooms_raw = supabase.table("rooms").select("*").eq("project_id", project_id).order("room_number").execute()
                export_data = []
                for r in rooms_raw.data:
                    row = {"room_number": r["room_number"], "room_name_planned": r["room_name_planned"]}
                    p_json = r.get("parameters") or {}
                    for p in mapped_params: row[p] = p_json.get(p, "")
                    export_data.append(row)
                
                df_export = pd.DataFrame(export_data) if export_data else pd.DataFrame(columns=["room_number", "room_name_planned"] + mapped_params)
                
                buffer_exp = io.BytesIO()
                with pd.ExcelWriter(buffer_exp, engine='xlsxwriter') as writer:
                    df_export.to_excel(writer, index=False, sheet_name='Locali')
                
                st.download_button("⬇️ Scarica Elenco/Template", data=buffer_exp.getvalue(), file_name=f"locali_{selected_label}.xlsx")

            with col_ex2:
                st.write("**Importa**")
                up_rooms = st.file_uploader("Carica file Locali", type=["xlsx", "csv"], key="up_rooms")
                if up_rooms and st.button("🚀 Avvia Importazione Locali"):
                    df_up = pd.read_excel(up_rooms) if up_rooms.name.endswith('.xlsx') else pd.read_csv(up_rooms)
                    count_imp = 0
                    for _, row in df_up.iterrows():
                        r_num = str(row.get("room_number", "")).strip()
                        r_name = str(row.get("room_name_planned", "")).strip()
                        if r_num:
                            # Estraiamo i parametri che corrispondono alla mappatura
                            params_to_save = {p: str(row[p]) for p in mapped_params if p in row and pd.notna(row[p])}
                            # Upsert (Aggiorna se esiste il numero, altrimenti inserisce - logica semplificata qui come insert)
                            supabase.table("rooms").insert({
                                "project_id": project_id,
                                "room_number": r_num,
                                "room_name_planned": r_name,
                                "parameters": params_to_save
                            }).execute()
                            count_imp += 1
                    st.success(f"Importati/Aggiornati {count_imp} locali!")
                    st.rerun()

        st.divider()

        # Visualizzazione Editor
        rooms_resp = supabase.table("rooms").select("*").eq("project_id", project_id).order("room_number").execute()
        if rooms_resp.data:
            flat_data = []
            for r in rooms_resp.data:
                row = {"id": r["id"], "room_number": r["room_number"], "room_name_planned": r["room_name_planned"]}
                params_json = r.get("parameters") or {}
                for p in mapped_params: row[p] = params_json.get(p, "")
                flat_data.append(row)

            df_rooms = pd.DataFrame(flat_data)
            edited_df = st.data_editor(
                df_rooms,
                column_config={"id": None, "room_number": st.column_config.TextColumn("Numero", disabled=True)},
                use_container_width=True, hide_index=True, key="editor_locali"
            )

            if st.button("💾 Salva Modifiche Editor"):
                for _, row in edited_df.iterrows():
                    updated_params = {p: row[p] for p in mapped_params if p in row}
                    supabase.table("rooms").update({
                        "room_name_planned": row["room_name_planned"],
                        "parameters": updated_params
                    }).eq("id", row["id"]).execute()
                st.success("Modifiche salvate!")
                st.rerun()
        else:
            st.info("Nessun locale trovato. Usa l'importazione Excel o la sidebar per aggiungerne uno.")

        with st.sidebar.expander("➕ Aggiungi Singolo Locale"):
            with st.form("new_room_form"):
                n_num = st.text_input("Numero")
                n_nam = st.text_input("Nome")
                if st.form_submit_button("Aggiungi"):
                    supabase.table("rooms").insert({"room_number": n_num, "room_name_planned": n_nam, "project_id": project_id, "parameters": {}}).execute()
                    st.rerun()

    # --- 2. PAGINA: MAPPATURA PARAMETRI (INVARIATA) ---
    elif menu == "Mappatura Parametri":
        with st.expander("📥 Importazione Massiva Mappature"):
            template_df = pd.DataFrame(columns=["Database", "Revit"])
            buffer_map = io.BytesIO()
            with pd.ExcelWriter(buffer_map, engine='xlsxwriter') as writer:
                template_df.to_excel(writer, index=False)
            st.download_button("⬇️ Scarica Template Mappe", data=buffer_map.getvalue(), file_name="template_mappe.xlsx")
            
            up_map = st.file_uploader("Carica file Mappe", type=["xlsx", "csv"])
            if up_map and st.button("🚀 Conferma Import Mappe"):
                df_m = pd.read_excel(up_map) if up_map.name.endswith('.xlsx') else pd.read_csv(up_map)
                batch = [{"project_id": project_id, "db_column_name": str(r['Database']).strip(), "revit_parameter_name": str(r['Revit']).strip()} for _, r in df_m.dropna().iterrows()]
                supabase.table("parameter_mappings").insert(batch).execute()
                st.rerun()

        st.subheader("➕ Aggiungi Singola Mappatura")
        with st.form("single_map"):
            c1, c2 = st.columns(2)
            db_c = c1.text_input("Chiave Database")
            rev_p = c2.text_input("Parametro Revit")
            if st.form_submit_button("Salva"):
                supabase.table("parameter_mappings").insert({"project_id": project_id, "db_column_name": db_c, "revit_parameter_name": rev_p}).execute()
                st.rerun()

        res_map = supabase.table("parameter_mappings").select("*").eq("project_id", project_id).execute()
        if res_map.data:
            st.subheader("📋 Mappature Attive")
            st.dataframe(pd.DataFrame(res_map.data)[["db_column_name", "revit_parameter_name"]], use_container_width=True, hide_index=True)
            if st.button("🗑️ Reset Mappature"):
                supabase.table("parameter_mappings").delete().eq("project_id", project_id).execute()
                st.rerun()

# --- 3. PAGINA: GESTIONE PROGETTI (INVARIATA) ---
elif menu == "Gestione Progetti":
    st.title("⚙️ Gestione Progetti")
    t1, t2 = st.tabs(["➕ Nuovo Progetto", "📝 Modifica / Elimina"])
    with t1:
        with st.form("new_prj"):
            cp = st.text_input("Codice")
            np = st.text_input("Nome")
            if st.form_submit_button("Crea"):
                supabase.table("projects").insert({"project_code": cp, "project_name": np}).execute()
                st.rerun()
    with t2:
        if projects_list:
            proj_sel = st.selectbox("Progetto:", {f"{p['project_code']} - {p['project_name']}": p for p in projects_list}.keys())
            target = {f"{p['project_code']} - {p['project_name']}": p for p in projects_list}[proj_sel]
            new_c = st.text_input("Codice", value=target['project_code'])
            new_n = st.text_input("Nome", value=target['project_name'])
            if st.button("💾 Salva Modifiche"):
                supabase.table("projects").update({"project_code": new_c, "project_name": new_n}).eq("id", target['id']).execute()
                st.rerun()
            st.divider()
            conf = st.text_input("Scrivi 'ELIMINA'")
            if st.button("🔥 Elimina Progetto") and conf == "ELIMINA":
                supabase.table("projects").delete().eq("id", target['id']).execute()
                st.rerun()
