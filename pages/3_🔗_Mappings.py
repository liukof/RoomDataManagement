import streamlit as st
import pandas as pd
from supabase import create_client

url, key = st.secrets["SUPABASE_URL"], st.secrets["SUPABASE_KEY"]
supabase = create_client(url, key)

if not st.session_state.get("user_data"):
    st.switch_page("app.py")
    st.stop()

# ... (Logica di selezione progetto identica alle altre pagine)
# [Omettendo ripetizione per brevità, usa lo stesso blocco Sidebar/Project Context]

st.header("🔗 Revit Parameter Mapping")

with st.expander("📥 Import / Export Mappings"):
    c1, c2 = st.columns(2)
    with c1:
        maps = supabase.table("parameter_mappings").select("*").eq("project_id", project_id).execute().data
        if maps:
            df_m_exp = pd.DataFrame(maps)[["db_column_name", "revit_parameter_name"]]
            buf = io.BytesIO()
            with pd.ExcelWriter(buf, engine='xlsxwriter') as writer: df_m_exp.to_excel(writer, index=False)
            st.download_button("⬇️ Download Excel", data=buf.getvalue(), file_name="mappings.xlsx")
    with c2:
        up_m = st.file_uploader("Upload Mappings XLSX", type=["xlsx"])
        if up_m and st.button("🚀 Upload"):
            df_m_up = pd.read_excel(up_m, dtype=str)
            m_bulk = [{"project_id": project_id, "db_column_name": str(row["db_column_name"]), "revit_parameter_name": str(row["revit_parameter_name"])} for _, row in df_m_up.iterrows()]
            supabase.table("parameter_mappings").upsert(m_bulk, on_conflict="project_id,db_column_name").execute()
            st.success("Mappings updated!"); st.rerun()

with st.form("new_mapping"):
    c1, c2 = st.columns(2)
    dbp = c1.text_input("Database Column Name (es: finitura_pavimento)")
    rvp = c2.text_input("Revit Parameter Name (es: Revit_Floor_Finish)")
    if st.form_submit_button("Add Mapping"):
        if dbp and rvp:
            supabase.table("parameter_mappings").insert({"project_id": project_id, "db_column_name": dbp, "revit_parameter_name": rvp}).execute()
            st.rerun()

# Tabella editabile per cancellazione
maps_data = supabase.table("parameter_mappings").select("*").eq("project_id", project_id).execute().data
if maps_data:
    df_m = pd.DataFrame(maps_data)[["id", "db_column_name", "revit_parameter_name"]]
    df_m.insert(0, "Select", False)
    ed_m = st.data_editor(df_m, use_container_width=True, hide_index=True, column_config={"id": None})
    if st.button("🗑️ Delete Mappings"):
        ids = [int(i) for i in ed_m[ed_m["Select"] == True]["id"].tolist()]
        if ids: 
            supabase.table("parameter_mappings").delete().in_("id", ids).execute()
            st.rerun()
