import streamlit as st
import io
import os
# Add root to sys.path if needed, though running via `streamlit run streamlit_cotizador/app.py` from root works usually.
# But for imports to work inside the package, we might need relative imports or package structure.
# Since I'm running `streamlit run streamlit_cotizador/app.py`, `streamlit_cotizador` is a package if I have __init__.py.
# But usually adding to path is safer.
import sys
sys.path.append(os.getcwd())

from streamlit_cotizador.utils import ExtractionSchema, ItemMaterial, ItemPersonal, ItemActividad, transcribir_audio, extraer_informacion, llenar_pdf, enviar_correos

# Constants
DEFAULT_QUOTE = {
    "id": 0,
    "folio": "1",
    "audio_bytes": None,
    "transcription": "",
    "is_analyzed": False,
    "extraction_data": None, # instance of ExtractionSchema
    "edited_data": None,     # dict for data editor
    "pdf_generated": False
}

def main():
    st.set_page_config(page_title="Cotizador por Voz", layout="wide")

    # Initialize Session State
    if "quotes" not in st.session_state:
        st.session_state.quotes = [DEFAULT_QUOTE.copy()]

    if "current_quote_index" not in st.session_state:
        st.session_state.current_quote_index = 0

    # Helper to get current quote
    def get_current_quote():
        return st.session_state.quotes[st.session_state.current_quote_index]

    # Sidebar
    with st.sidebar:
        st.header("Configuración")

        # API Key
        # Check environment variable first, then secrets
        env_key = os.environ.get("GROQ_API_KEY", "")
        if not env_key:
            try:
                env_key = st.secrets.get("GROQ_API_KEY", "")
            except FileNotFoundError:
                pass

        groq_api_key = st.text_input("GROQ API Key", value=env_key, type="password", help="Ingresa tu API Key de Groq")

        if not groq_api_key:
            st.warning("Se requiere API Key para continuar.")
            st.stop()

        # PDF Template
        pdf_template = st.file_uploader("Plantilla PDF Base", type=["pdf"])

        st.divider()
        st.subheader("Configuración Correo")
        email_sender = st.text_input("Gmail Sender")
        email_password = st.text_input("App Password", type="password")
        dest1 = st.text_input("Destinatario 1")
        dest2 = st.text_input("Destinatario 2")
        dest3 = st.text_input("Destinatario 3")

        st.divider()
        st.subheader("Gestión de Cotizaciones")

        # Quote Selector
        quote_options = [f"Cotización #{q['folio']}" for q in st.session_state.quotes]
        selected_quote_str = st.selectbox(
            "Seleccionar Cotización",
            options=quote_options,
            index=st.session_state.current_quote_index,
            key="quote_selector"
        )

        # Update current index based on selection
        # We use the key callback or check manually
        new_index = quote_options.index(selected_quote_str)
        if new_index != st.session_state.current_quote_index:
            st.session_state.current_quote_index = new_index
            st.rerun()

        # New Quote Button
        if st.button("➕ Nueva Cotización"):
            new_id = len(st.session_state.quotes)
            new_folio = str(new_id + 1)
            new_quote = DEFAULT_QUOTE.copy()
            new_quote["id"] = new_id
            new_quote["folio"] = new_folio
            st.session_state.quotes.append(new_quote)
            st.session_state.current_quote_index = new_id
            st.rerun()

    # Main Content Area
    current_quote = get_current_quote()
    st.title(f"Cotización #{current_quote['folio']}")

    # --- 1. Audio Recording & Playback ---
    st.header("1. Grabación de Audio")

    # Unique key for each quote's audio input
    audio_val = st.audio_input("Grabar Audio", key=f"audio_input_{current_quote['id']}")

    # If new audio is recorded, update session state
    if audio_val:
        # Read bytes only if not already saved or if it changed
        # st.audio_input returns a file-like object.
        # We need to handle this carefully.
        # If we read it, we should store it.
        # But st.audio_input re-runs on interaction.
        audio_val.seek(0)
        bytes_data = audio_val.read()
        if current_quote['audio_bytes'] != bytes_data:
            current_quote['audio_bytes'] = bytes_data
            # Reset extraction status if audio changes
            current_quote['is_analyzed'] = False
            current_quote['transcription'] = ""
            st.rerun()

    # Display persistent audio player if bytes exist
    if current_quote['audio_bytes']:
        st.write("Audio grabado:")
        st.audio(current_quote['audio_bytes'], format="audio/wav")

    # --- 2. Transcription ---
    st.header("2. Transcripción y Edición")

    if current_quote['audio_bytes']:
        if st.button("📝 Transcribir Audio", key=f"btn_transcribe_{current_quote['id']}"):
            with st.spinner("Transcribiendo con Groq/Whisper..."):
                # Create a file-like object from bytes for the API
                audio_file = io.BytesIO(current_quote['audio_bytes'])
                audio_file.name = "audio.wav"

                text = transcribir_audio(groq_api_key, audio_file)

                if "Error" in text:
                    st.error(text)
                else:
                    current_quote['transcription'] = text
                    st.success("Transcripción completada.")
                    st.rerun()

    # Editable Text Area
    if current_quote['transcription']:
        transcription_val = st.text_area(
            "Edita la transcripción si es necesario:",
            value=current_quote['transcription'],
            height=300,
            key=f"text_area_{current_quote['id']}"
        )

        # Update session state on change
        if transcription_val != current_quote['transcription']:
            current_quote['transcription'] = transcription_val
            # If text changes, we might want to reset analysis or just keep it?
            # Let's keep analysis but maybe warn user? Or reset?
            # Resetting analysis is safer to ensure consistency.
            if current_quote['is_analyzed']:
                st.warning("Has modificado el texto. Recuerda volver a 'Procesar/Analizar' para actualizar los datos.")

    # --- 3. Extraction & Analysis ---
    st.header("3. Análisis y Edición de Datos")

    if current_quote['transcription']:
        if st.button("🔍 Procesar / Analizar Información", key=f"btn_analyze_{current_quote['id']}"):
            with st.spinner("Analizando texto con IA (LangChain)..."):
                res = extraer_informacion(groq_api_key, current_quote['transcription'])

                if res.get("error"):
                    st.error(f"Error en análisis: {res['error']}")
                else:
                    extraction = res["extraction"]
                    current_quote['extraction_data'] = extraction
                    current_quote['is_analyzed'] = True

                    # Prepare initial edited data from extraction
                    # Convert pydantic models to dicts for data_editor
                    current_quote['edited_data'] = {
                        "lista_materiales": [m.dict() for m in extraction.lista_materiales],
                        "lista_personal": [p.dict() for p in extraction.lista_personal]
                    }
                    st.success("Análisis completado. Revisa y edita los datos abajo.")
                    st.rerun()

    # Data Editor Section
    if current_quote['is_analyzed'] and current_quote['edited_data']:
        st.divider()
        st.subheader("🛠️ Edición de Materiales y Costos")

        # --- MATERIALES ---
        st.markdown("**Lista de Materiales**")

        edited_materiales = st.data_editor(
            current_quote['edited_data']['lista_materiales'],
            num_rows="dynamic",
            key=f"editor_materiales_{current_quote['id']}",
            use_container_width=True,
            column_config={
                "cantidad": st.column_config.TextColumn("Cantidad"),
                "unidad": st.column_config.TextColumn("Unidad"),
                "descripcion": st.column_config.TextColumn("Descripción", width="large"),
                "costo": st.column_config.TextColumn("Costo Unitario"),
                "total": st.column_config.TextColumn("Total (Auto)", disabled=True)
            }
        )

        # --- PERSONAL ---
        st.markdown("**Lista de Personal / Mano de Obra**")

        edited_personal = st.data_editor(
            current_quote['edited_data']['lista_personal'],
            num_rows="dynamic",
            key=f"editor_personal_{current_quote['id']}",
            use_container_width=True,
            column_config={
                "cantidad_personas": st.column_config.TextColumn("Cant. Personas"),
                "categoria": st.column_config.TextColumn("Categoría", width="large"),
                "salario_semanal": st.column_config.TextColumn("Salario Semanal"),
                "semanas_cotizadas": st.column_config.TextColumn("Semanas"),
                "salario_neto": st.column_config.TextColumn("Total (Auto)", disabled=True)
            }
        )

        # --- DYNAMIC RECALCULATION ---
        # Update session state with edited values
        current_quote['edited_data']['lista_materiales'] = edited_materiales
        current_quote['edited_data']['lista_personal'] = edited_personal

        # Calculate Totals
        total_materiales = 0.0
        for item in edited_materiales:
            try:
                c = float(str(item.get("cantidad", "0")).replace(',', ''))
                p = float(str(item.get("costo", "0")).replace('$', '').replace(',', ''))
                subtotal = c * p
                item["total"] = f"{subtotal:,.2f}"
                total_materiales += subtotal
            except (ValueError, TypeError):
                item["total"] = "Error"

        total_personal = 0.0
        total_personas_count = 0
        for item in edited_personal:
            try:
                c = float(str(item.get("cantidad_personas", "0")))
                s = float(str(item.get("salario_semanal", "0")).replace('$', '').replace(',', ''))
                w = float(str(item.get("semanas_cotizadas", "0")))
                subtotal = c * s * w
                item["salario_neto"] = f"{subtotal:,.2f}"
                total_personal += subtotal
                total_personas_count += int(c)
            except (ValueError, TypeError):
                item["salario_neto"] = "Error"

        # Update totals in extraction_data (for PDF generation)
        # Note: We are updating the Pydantic model in extraction_data roughly,
        # or we should just use edited_data for PDF generation.
        # The prompt says: "El botón de descarga ... debe tomar los datos finales de las tablas editadas"
        # So we should rely on edited_data.

        # Display Calculated Totals
        c1, c2, c3 = st.columns(3)
        c1.metric("Total Materiales", f"${total_materiales:,.2f}")
        c2.metric("Total Mano de Obra", f"${total_personal:,.2f}")
        c3.metric("Total Personas", f"{total_personas_count}")

        st.caption("*Los totales se recalculan automáticamente al editar la tabla.*")

    # --- 4. Export & Email ---
    st.header("4. Exportar y Enviar")

    if current_quote['is_analyzed'] and current_quote['edited_data']:
        # Prepare data for export
        # We need to reconstruct the ExtractionSchema with edited values
        # We take the original extraction data and update the lists

        # Use copy() to avoid modifying original schema in place if we want to revert?
        # Pydantic models are mutable.
        # But extraction_data is stored in session_state.
        # It's safer to create a new object or modify a copy.
        # But copy() on pydantic v1 is different from v2. Here we use pydantic v2 (from pip install).
        # v2 uses model_copy() or standard copy.
        # Let's just create a new instance or modify a copy.
        final_data = current_quote['extraction_data'].model_copy(deep=True)

        # Update lists from edited data
        # Note: edited_data items are dicts, we need to convert back to Pydantic models
        final_data.lista_materiales = [ItemMaterial(**m) for m in current_quote['edited_data']['lista_materiales']]
        final_data.lista_personal = [ItemPersonal(**p) for p in current_quote['edited_data']['lista_personal']]

        # Update totals in schema (important for PDF)
        # These variables (total_materiales, total_personas_count) come from the calculation block above
        # We need to ensure they are available in this scope. They are local variables in main(), so yes.
        final_data.total_general_materiales = f"{total_materiales:,.2f}"
        final_data.total_personas_count = str(total_personas_count)

        # ASSIGN FOLIO FROM SESSION (Review Fix)
        final_data.folio = str(current_quote['folio'])

        # PDF Generation
        if pdf_template:
            if st.button("📄 Generar PDF de Cotización", key=f"btn_pdf_{current_quote['id']}"):
                with st.spinner("Generando PDF..."):
                    output_buffer = io.BytesIO()
                    # Reset template file pointer
                    pdf_template.seek(0)
                    success = llenar_pdf(final_data, pdf_template, output_buffer)

                    if success:
                        current_quote['pdf_generated'] = True
                        current_quote['pdf_buffer'] = output_buffer
                        st.success("PDF Generado exitosamente.")
                    else:
                        st.error("Error al generar el PDF.")

        elif not pdf_template:
             st.info("⚠️ Carga una plantilla PDF en la barra lateral para habilitar la generación de PDF.")

        # Download Button
        if current_quote.get('pdf_generated') and current_quote.get('pdf_buffer'):
            # Filename logic
            clean_name = "".join(c for c in final_data.requisitor if c.isalnum() or c in (' ', '_', '-')).strip()
            if not clean_name: clean_name = "Cotizacion"
            filename = f"{clean_name}.pdf"

            st.download_button(
                label="⬇️ Descargar PDF",
                data=current_quote['pdf_buffer'].getvalue(),
                file_name=filename,
                mime="application/pdf",
                key=f"dl_pdf_{current_quote['id']}"
            )

        # Email Sending
        st.divider()
        st.subheader("📧 Enviar por Correo")

        if st.button("Enviar Reporte por Correo", key=f"btn_email_{current_quote['id']}"):
            if not (email_sender and email_password and dest1 and dest2 and dest3):
                st.error("Faltan configuraciones de correo (Remitente, Password o Destinatarios).")
            else:
                with st.spinner("Enviando correos..."):
                    dests = [dest1, dest2, dest3]
                    res_email = enviar_correos(final_data, email_sender, email_password, dests)
                    if "EXITO" in res_email:
                        st.success(res_email)
                    else:
                        st.error(res_email)

if __name__ == "__main__":
    main()
