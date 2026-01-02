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

    # --- 1. PAGINA: LOCALI ---
    if menu == "Locali":
        maps_resp = supabase.table("parameter_mappings").select("db_column_name").eq("project_id", project_id).execute()
        mapped_params = [m['db_column_name'] for m in maps_resp.data]

        with st.expander("📥 Import / Export / Reset Locali"):
            c_ex1, c_ex2, c_ex3 = st.columns(3)
            with c_ex1:
                st.write("**Esporta**")
                rooms_raw = supabase.table("rooms").select("*").eq("project_id", project_id).order("room_number").execute()
                export_data = []
                for r in rooms_raw.data:
                    row = {"room_number": r["room_number"], "room_name_planned": r["room_name_planned"]}
                    p_json = r.get("parameters") or {}
                    for p in mapped_params: row[p] = p_json.get(p, "")
                    export_data.append(row)
                df_export = pd.DataFrame(export_data) if export_data else pd.DataFrame(columns=["room_number", "room_name_planned"] + mapped_params)
                buf = io.BytesIO()
                with pd.ExcelWriter(buf, engine='xlsxwriter') as writer:
                    df_export.to_excel(writer, index=False)
                st.download_button("⬇️ Scarica Excel Locali", data=buf.getvalue(), file_name=f"locali_{selected_label}.xlsx")

            with c_ex2:
                st.write("**Importa (Upsert)**")
                up_rooms = st.file_uploader("Carica file Locali", type=["xlsx", "csv"], key="up_rooms_file")
                if up_rooms and st.button("🚀 Sincronizza Locali"):
                    df_up = pd.read_excel(up_rooms) if up_rooms.name.endswith('.xlsx') else pd.read_csv(up_rooms)
                    for _, row in df_up.iterrows():
                        r_num = str(row.get("room_number", "")).strip()
                        if r_num:
                            p_save = {p: str(row[p]) for p in mapped_params if p in row and pd.notna(row[p])}
                            exist = supabase.table("rooms").select("id").eq("project_id", project_id).eq("room_number", r_num).execute()
                            payload = {"project_id": project_id, "room_number": r_num, "room_name_planned": str(row.get("room_name_planned", "")), "parameters": p_save}
                            if exist.data: supabase.table("rooms").update(payload).eq("id", exist.data[0]["id"]).execute()
                            else: supabase.table("rooms").insert(payload).execute()
                    st.success("Sincronizzazione completata!")
                    st.rerun()

            with c_ex3:
                st.write("**Zona Pericolo**")
                if st.button("🗑️ SVUOTA TUTTI I LOCALI"):
                    supabase.table("rooms").delete().eq("project_id", project_id).execute()
                    st.rerun()

        st.divider()

        rooms_resp = supabase.table("rooms").select("*").eq("project_id", project_id).order("room_number").execute()
        if rooms_resp.data:
            flat_data = []
            for r in rooms_resp.data:
                row = {"id": r["id"], "room_number": r["room_number"], "room_name_planned": r["room_name_planned"]}
                p_json = r.get("parameters") or {}
                for p in mapped_params: row[p] = p_json.get(p, "")
                flat_data.append(row)

            df_rooms = pd.DataFrame(flat_data)
            df_rooms["Elimina"] = False
            st.subheader("📝 Editor Locali")
            edited_df = st.data_editor(df_rooms, column_config={"id": None, "room_number": st.column_config.TextColumn("Numero", disabled=True), "Elimina": st.column_config.CheckboxColumn("Seleziona")}, use_container_width=True, hide_index=True, key="editor_locali")

            col_btn1, col_btn2 = st.columns(2)
            with col_btn1:
                if st.button("💾 SALVA MODIFICHE DATI", use_container_width=True, type="primary"):
                    for _, row in edited_df.iterrows():
                        up_p = {p: row[p] for p in mapped_params if p in row}
                        supabase.table("rooms").update({"room_name_planned": row["room_name_planned"], "parameters": up_p}).eq("id", row["id"]).execute()
                    st.rerun()
            with col_btn2:
                if st.button("🗑️ ELIMINA RIGHE SELEZIONATE", use_container_width=True):
                    to_del = edited_df[edited_df["Elimina"] == True]
                    for _, r in to_del.iterrows(): supabase.table("rooms").delete().eq("id", r["id"]).execute()
                    st.rerun()
        else:
            st.info("Nessun locale trovato.")

    # --- 2. PAGINA: MAPPATURA PARAMETRI ---
    elif menu == "Mappatura Parametri":
        # RIPRISTINATO: Import/Export Mappature
        with st.expander("📥 Import / Export Mappature (Excel)"):
            c_m1, c_m2 = st.columns(2)
            with c_m1:
                st.write("**Esporta / Template**")
                res_m = supabase.table("parameter_mappings").select("*").eq("project_id", project_id).execute()
                df_m_exp = pd.DataFrame(res_m.data)[["db_column_name", "revit_parameter_name"]] if res_m.data else pd.DataFrame(columns=["Database", "Revit"])
                df_m_exp.columns = ["Database", "Revit"]
                buf_m = io.BytesIO()
                with pd.ExcelWriter(buf_m, engine='xlsxwriter') as writer:
                    df_m_exp.to_excel(writer, index=False)
                st.download_button("⬇️ Scarica Template Mappe", data=buf_m.getvalue(), file_name="mappatura_parametri.xlsx")
            
            with c_m2:
                st.write("**Importa Mappe**")
                up_m = st.file_uploader("Carica file Mappe", type=["xlsx", "csv"])
                if up_m and st.button("🚀 Carica Mappature"):
                    df_m_up = pd.read_excel(up_m) if up_m.name.endswith('.xlsx') else pd.read_csv(up_m)
                    batch = [{"project_id": project_id, "db_column_name": str(r['Database']).strip(), "revit_parameter_name": str(r['Revit']).strip()} for _, r in df_m_up.dropna().iterrows()]
                    supabase.table("parameter_mappings").insert(batch).execute()
                    st.rerun()

        st.subheader("➕ Aggiungi Singola Mappatura")
        with st.form("single_map"):
            c1, c2 = st.columns(2)
            db_c = c1.text_input("Chiave Database (es. Fire_Rating)")
            rev_p = c2.text_input("Parametro Revit (es. Fire Rating)")
            if st.form_submit_button("Salva Mappatura"):
                if db_c and rev_p:
                    supabase.table("parameter_mappings").insert({"project_id": project_id, "db_column_name": db_c, "revit_parameter_name": rev_p}).execute()
                    st.rerun()

        res_map = supabase.table("parameter_mappings").select("*").eq("project_id", project_id).execute()
        if res_map.data:
            st.subheader("📋 Mappature Attive")
            df_m_view = pd.DataFrame(res_map.data)
            df_m_view["Elimina"] = False
            ed_map = st.data_editor(df_m_view[["id", "db_column_name", "revit_parameter_name", "Elimina"]], column_config={"id": None, "Elimina": st.column_config.CheckboxColumn("🗑️")}, hide_index=True, use_container_width=True)
            if st.button("Conferma Eliminazione Mappature"):
                for _, r in ed_map.iterrows():
                    if r["Elimina"]: supabase.table("parameter_mappings").delete().eq("id", r["id"]).execute()
                st.rerun()

# --- 3. PAGINA: GESTIONE PROGETTI ---
elif menu == "Gestione Progetti":
    st.title("⚙️ Gestione Progetti")
    t1, t2 = st.tabs(["➕ Nuovo Progetto", "📝 Modifica / Elimina"])
    with t1:
        with st.form("new_prj"):
            cp = st.text_input("Codice")
            np = st.text_input("Nome")
            if st.form_submit_button("Crea Progetto"):
                if cp and np:
                    supabase.table("projects").insert({"project_code": cp, "project_name": np}).execute()
                    st.rerun()
    with t2:
        if projects_list:
            proj_sel = st.selectbox("Progetto:", {f"{p['project_code']} - {p['project_name']}": p for p in projects_list}.keys())
            target = {f"{p['project_code']} - {p['project_name']}": p for p in projects_list}[proj_sel]
            new_c = st.text_input("Codice", value=target['project_code'])
            new_n = st.text_input("Nome", value=target['project_name'])
            col_p1, col_p2 = st.columns(2)
            if col_p1.button("💾 Salva Modifiche Nome"):
                supabase.table("projects").update({"project_code": new_c, "project_name": new_n}).eq("id", target['id']).execute()
                st.rerun()
            if col_p2.button("🔥 ELIMINA PROGETTO"):
                supabase.table("projects").delete().eq("id", target['id']).execute()
                st.rerun()
