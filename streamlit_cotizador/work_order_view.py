import streamlit as st
import pandas as pd
from datetime import datetime
import io
import sys
import os

# Ensure api is importable
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from api.services.work_order import process_and_save_work_order, get_next_sequence
from api.ai_utils import transcribir_audio, extraer_informacion

def render_work_order_view():
    st.title("Pre Work Order")

    # --- Session State Initialization ---
    if "wo_data" not in st.session_state:
        # Initialize with default structure similar to index.html
        st.session_state.wo_data = {
            "cliente": "",
            "requisitor": "",
            "contacto": "",
            "celular": "",
            "fechaCotizacion": datetime.now().strftime("%Y-%m-%d"),
            "fechaEntrega": "",
            "prioridad": "AAA - Alta Prioridad",
            "conceptoDesc": "",
            "tipoTrabajo": "MANTENIMIENTO", # Default
            "materiales": [],
            "manoObra": [],
            "herramientas": [],
            "equipos": [],
            "programa": [], # Unified list for simplicity or separated sections
            "restricciones": {
                "produccion": "", "seguridad": "", "dificultad": "", "horarios": "", "especificidad": ""
            }
        }

        # Predict Folio
        seq = get_next_sequence("WORKORDER_SEQ", increment=False)
        st.session_state.wo_folio_preview = f"{seq} (Predictivo)"

    # --- AI Assistant ---
    with st.expander("🤖 Asistente IA (Dictado)", expanded=True):
        st.info("Graba las instrucciones. La IA llenará el formulario automáticamente.")

        # API Key handling
        groq_key = os.environ.get("GROQ_API_KEY") or st.secrets.get("GROQ_API_KEY")
        if not groq_key:
            groq_key = st.text_input("Groq API Key", type="password")

        audio_val = st.audio_input("Grabar Instrucciones")

        if audio_val and st.button("Procesar Audio"):
            if not groq_key:
                st.error("Falta API Key")
            else:
                with st.spinner("Procesando..."):
                    # Read bytes
                    audio_bytes = audio_val.read()

                    # Transcribe
                    text = transcribir_audio(groq_key, audio_bytes)
                    if "Error" in text:
                        st.error(text)
                    else:
                        st.write(f"**Transcripción:** {text}")

                        # Extract
                        res = extraer_informacion(groq_key, text)
                        if res.get("error"):
                            st.error(res["error"])
                        else:
                            data = res["extraction"]
                            # Map to Session State
                            wo = st.session_state.wo_data

                            if data.get("cliente"): wo["cliente"] = data["cliente"]
                            if data.get("requisitor"): wo["requisitor"] = data["requisitor"]
                            if data.get("contacto"): wo["contacto"] = data["contacto"]
                            if data.get("descripcion_generica"): wo["conceptoDesc"] = data["descripcion_generica"]
                            if data.get("tipo_de_trabajo"): wo["tipoTrabajo"] = data["tipo_de_trabajo"]

                            # Resources
                            if data.get("lista_materiales"):
                                for m in data["lista_materiales"]:
                                    wo["materiales"].append({
                                        "quantity": m.get("cantidad", ""),
                                        "unit": m.get("unidad", ""),
                                        "description": m.get("descripcion", ""),
                                        "cost": str(m.get("costo", "")).replace("$","").replace(",",""),
                                        "total": str(m.get("total", "")).replace("$","").replace(",","")
                                    })

                            if data.get("lista_personal"):
                                for p in data["lista_personal"]:
                                    wo["manoObra"].append({
                                        "category": p.get("categoria", ""),
                                        "salary": str(p.get("salario_semanal", "")).replace("$","").replace(",",""),
                                        "personnel": p.get("cantidad_personas", ""),
                                        "weeks": p.get("semanas_cotizadas", ""),
                                        "total": str(p.get("salario_neto", "")).replace("$","").replace(",","")
                                    })

                            # Tools (Simple list in extraction, mapping to dict)
                            if data.get("lista_herramientas"):
                                for t in data["lista_herramientas"]:
                                    wo["herramientas"].append({"description": t, "quantity": "1", "unit": "pza"})

                            # Restrictions
                            if data.get("restricciones_produccion"): wo["restricciones"]["produccion"] = data["restricciones_produccion"]
                            if data.get("restricciones_seguridad"): wo["restricciones"]["seguridad"] = data["restricciones_seguridad"]

                            st.success("Información extraída y formulario actualizado.")
                            st.rerun()

    # --- Form Layout ---
    st.divider()

    col1, col2, col3, col4 = st.columns(4)
    with col1:
        st.metric("Folio (Prev)", st.session_state.wo_folio_preview)
    with col2:
        st.date_input("Fecha", value=datetime.now(), disabled=True)
    with col3:
        st.session_state.wo_data["fechaEntrega"] = st.date_input("Fecha Entrega")
    with col4:
        st.session_state.wo_data["prioridad"] = st.selectbox("Prioridad", ["AAA - Alta Prioridad", "AA - Media Prioridad", "A - Baja Prioridad"], index=0)

    # Client Info
    st.subheader("Información del Cliente")
    c1, c2 = st.columns(2)
    with c1:
        st.session_state.wo_data["cliente"] = st.text_input("Cliente", st.session_state.wo_data["cliente"])
        st.session_state.wo_data["requisitor"] = st.text_input("Requisitor", st.session_state.wo_data["requisitor"])
    with c2:
        st.session_state.wo_data["contacto"] = st.text_input("Contacto", st.session_state.wo_data["contacto"])
        st.session_state.wo_data["tipoTrabajo"] = st.selectbox("Tipo de Trabajo",
            ["MANTENIMIENTO", "CONSTRUCCION", "ELECTROMECANICA", "HVAC", "MAQUINARIA", "DISEÑO"],
            index=0 if not st.session_state.wo_data["tipoTrabajo"] else ["MANTENIMIENTO", "CONSTRUCCION", "ELECTROMECANICA", "HVAC", "MAQUINARIA", "DISEÑO"].index(st.session_state.wo_data["tipoTrabajo"]) if st.session_state.wo_data["tipoTrabajo"] in ["MANTENIMIENTO", "CONSTRUCCION", "ELECTROMECANICA", "HVAC", "MAQUINARIA", "DISEÑO"] else 0
        )

    # Description
    st.subheader("Descripción del Trabajo")
    st.session_state.wo_data["conceptoDesc"] = st.text_area("Concepto / Alcance", st.session_state.wo_data["conceptoDesc"], height=150)

    # Restrictions
    with st.expander("Restricciones y Riesgos"):
        r1, r2 = st.columns(2)
        st.session_state.wo_data["restricciones"]["produccion"] = r1.text_area("Restricciones Producción", st.session_state.wo_data["restricciones"]["produccion"])
        st.session_state.wo_data["restricciones"]["seguridad"] = r2.text_area("Restricciones Seguridad", st.session_state.wo_data["restricciones"]["seguridad"])

    # --- Tables (Resources) ---
    st.subheader("Recursos")

    tab_mat, tab_mo, tab_tool = st.tabs(["Materiales", "Mano de Obra", "Herramientas"])

    with tab_mat:
        # Data Editor for Materials
        # Convert list of dicts to DataFrame for better editing if needed, but data_editor handles list of dicts well.
        edited_mats = st.data_editor(
            st.session_state.wo_data["materiales"],
            num_rows="dynamic",
            column_config={
                "quantity": "Cant",
                "unit": "Unidad",
                "description": st.column_config.TextColumn("Descripción", width="large"),
                "cost": "Costo",
                "total": "Total"
            },
            key="editor_mats"
        )
        st.session_state.wo_data["materiales"] = edited_mats

    with tab_mo:
        edited_mo = st.data_editor(
            st.session_state.wo_data["manoObra"],
            num_rows="dynamic",
            column_config={
                "category": "Categoría",
                "salary": "Salario Semanal",
                "personnel": "Personal",
                "weeks": "Semanas",
                "total": "Total"
            },
            key="editor_mo"
        )
        st.session_state.wo_data["manoObra"] = edited_mo

    with tab_tool:
        edited_tools = st.data_editor(
            st.session_state.wo_data["herramientas"],
            num_rows="dynamic",
            column_config={
                "description": st.column_config.TextColumn("Descripción", width="large"),
                "quantity": "Cant",
                "unit": "Unidad"
            },
            key="editor_tools"
        )
        st.session_state.wo_data["herramientas"] = edited_tools

    # --- Actions ---
    st.divider()
    if st.button("💾 GUARDAR PRE WORK ORDER", type="primary", use_container_width=True):
        if not st.session_state.wo_data["cliente"] or not st.session_state.wo_data["conceptoDesc"]:
            st.warning("Falta Cliente o Descripción.")
        else:
            with st.spinner("Guardando en Google Sheets..."):
                # Construct Payload for Backend
                payload_item = {
                    "cliente": st.session_state.wo_data["cliente"],
                    "especialidad": st.session_state.wo_data["tipoTrabajo"], # Mapping
                    "concepto": st.session_state.wo_data["conceptoDesc"],
                    "responsable": "STREAMLIT_USER", # Placeholder
                    "prioridad": st.session_state.wo_data["prioridad"],
                    "fechaRespuesta": str(st.session_state.wo_data["fechaEntrega"]),
                    "materiales": st.session_state.wo_data["materiales"],
                    "manoObra": st.session_state.wo_data["manoObra"],
                    "herramientas": st.session_state.wo_data["herramientas"],
                    "restricciones": str(st.session_state.wo_data["restricciones"]),
                    # Add other fields as needed
                }

                try:
                    res = process_and_save_work_order([payload_item], "STREAMLIT_USER")
                    if res["success"]:
                        st.success(f"Guardado Exitosamente. Folios: {res['ids']}")
                        # Reset
                        st.session_state.wo_data["conceptoDesc"] = ""
                        st.session_state.wo_data["materiales"] = []
                        st.session_state.wo_data["manoObra"] = []
                    else:
                        st.error(f"Error: {res.get('message')}")
                except Exception as e:
                    st.error(f"Error interno: {str(e)}")
