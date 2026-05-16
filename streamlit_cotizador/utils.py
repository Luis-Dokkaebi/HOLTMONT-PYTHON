import os
import io
import smtplib
import ssl
from datetime import datetime
from typing import List, TypedDict, Optional
from email.message import EmailMessage

from pydantic import BaseModel, Field
from pypdf import PdfWriter, PdfReader
from pypdf.generic import NameObject, DictionaryObject, ArrayObject, FloatObject, BooleanObject

try:
    from groq import Groq
except ImportError:
    Groq = None

try:
    import ffmpeg
except ImportError:
    ffmpeg = None

try:
    from langchain_groq import ChatGroq
    from langchain_core.prompts import ChatPromptTemplate
    from langgraph.graph import StateGraph, END
except ImportError:
    ChatGroq = None

# --- DATA MODELS ---

class ItemPersonal(BaseModel):
    cantidad_personas: str = Field(default="", description="Número de personas para esta categoría.")
    categoria: str = Field(default="", description="Nombre del puesto (ej: Oficial Electricista, Ayudante).")
    salario_semanal: str = Field(default="", description="Salario semanal por persona.")
    semanas_cotizadas: str = Field(default="", description="Número de semanas que trabajarán.")
    salario_neto: str = Field(default="", description="Costo total de esta línea (Personas * Salario * Semanas).")

class ItemMaterial(BaseModel):
    cantidad: str = Field(default="", description="Cantidad numérica del material.")
    unidad: str = Field(default="", description="Unidad de medida (ej: pza, m, kgs).")
    descripcion: str = Field(default="", description="Nombre técnico del material.")
    costo: str = Field(default="", description="Costo unitario.")
    total: str = Field(default="", description="Total (Costo * Cantidad).")

class ItemActividad(BaseModel):
    descripcion: str = Field(default="", description="Descripción de la actividad.")
    tiempo: str = Field(default="", description="Duración estimada.")

class ExtractionSchema(BaseModel):
    """Extrae información técnica, logística y de costos para cotización."""

    # DATOS GENERALES
    folio: str = Field(default="", description="Número de folio aleatorio (4-6 dígitos).")
    fecha: str = Field(default="", description="Fecha actual (DD/MM/YYYY).")
    cliente: str = Field(default="", description="Nombre de la empresa cliente.")
    requisitor: str = Field(default="", description="Nombre del solicitante.")
    contacto: str = Field(default="", description="Correo o teléfono.")
    fecha_entrega: str = Field(default="", description="Fecha de entrega del proyecto.")
    actividad_programada: str = Field(default="", description="Título principal corto del trabajo.")

    tipo_de_trabajo: str = Field(
        default="",
        description="Tipo de servicio (Construcción, Remodelación, Reparación, Mantenimiento, etc)."
    )

    descripcion_generica: str = Field(
        default="",
        description="Resumen global técnico (Alcance general)."
    )

    # LISTAS PRINCIPALES
    programa_del_proyecto: List[ItemActividad] = Field(
        default_factory=list,
        description="Lista de pasos del cronograma.",
        max_length=5
    )

    lista_materiales: List[ItemMaterial] = Field(
        default_factory=list,
        description="Lista de materiales y costos.",
        max_length=4
    )

    # LISTAS DE RECURSOS
    lista_herramientas: List[str] = Field(
        default_factory=list,
        description="Lista de herramientas requeridas. Max 4 ítems.",
        max_length=4
    )
    lista_equipo_ligero: List[str] = Field(
        default_factory=list,
        description="Lista de equipo ligero. Max 4 ítems.",
        max_length=4
    )
    lista_equipo_proteccion: List[str] = Field(
        default_factory=list,
        description="Lista de EPP (Cascos, guantes, etc). Max 4 ítems.",
        max_length=4
    )

    # LISTA DE PERSONAL
    lista_personal: List[ItemPersonal] = Field(
        default_factory=list,
        description="Desglose de mano de obra (Puesto, Salario, Semanas).",
        max_length=4
    )

    total_personas_cantidad: str = Field(
        default="",
        description="Suma total de la columna 'cantidad_personas'."
    )

    # TOTAL GENERAL FINANCIERO (MATERIALES)
    total_general_materiales: str = Field(
        default="",
        description="Suma de los totales de la lista de materiales."
    )

class AgentState(TypedDict):
    input_text: str
    extraction: Optional[ExtractionSchema]
    error: str

# --- FUNCTIONS ---

def transcribir_audio(api_key: str, audio_file) -> str:
    """
    Transcribes audio using Groq API.
    audio_file: file-like object (BytesIO) containing the audio.
    """
    if not api_key:
        return "Error: Falta GROQ_API_KEY."
    
    try:
        # Prepare audio bytes
        audio_file.seek(0)
        audio_bytes = audio_file.read()
        filename = getattr(audio_file, "name", "audio.wav")

        # --- FFMPEG CONVERSION ---
        if ffmpeg:
            try:
                # Normalize to 16kHz mono wav
                process = (
                    ffmpeg
                    .input('pipe:0')
                    .output('pipe:1', format='wav', ac=1, ar='16000')
                    .run_async(pipe_stdin=True, pipe_stdout=True, pipe_stderr=True)
                )
                out, err = process.communicate(input=audio_bytes)

                if process.returncode == 0:
                    audio_bytes = out
                    filename = "converted_audio.wav"
                else:
                    print(f"FFmpeg warning: {err.decode('utf-8') if err else 'Unknown error'}")
            except Exception as e:
                print(f"FFmpeg error: {e}")
                # Continue with original content
        # -------------------------

        client = Groq(api_key=api_key)
        
        transcription = client.audio.transcriptions.create(
            file=(filename, audio_bytes),
            model="whisper-large-v3",
            response_format="json",
            language="es",
            temperature=0.0
        )
        return transcription.text
    except Exception as e:
        return f"Error en transcripción: {str(e)}"

def extraer_informacion(api_key: str, texto: str) -> dict:
    """
    Extracts structured information from text using LangChain/Groq.
    Returns a dictionary with 'extraction' (ExtractionSchema object) and 'error'.
    """
    if not api_key:
        return {"error": "Falta GROQ_API_KEY", "extraction": None}
    
    try:
        llm = ChatGroq(
            api_key=api_key,
            model="llama-3.3-70b-versatile",
            temperature=0,
            max_tokens=None,
            timeout=None,
            max_retries=2,
        )
        structured_llm = llm.with_structured_output(ExtractionSchema)
        
        fecha_actual = datetime.now().strftime("%d/%m/%Y")
        prompt = ChatPromptTemplate.from_messages([
            ("system", (
                f"Hoy es {fecha_actual}. Eres un ingeniero de costos y proyectos."
                "\n\nTU TAREA ES EXTRAER:"
                "\n1. Datos del Cliente y Proyecto."
                "\n2. Cronograma de actividades."
                "\n3. Lista de Materiales (con precios y totales)."
                "\n4. Recursos (Herramientas, Equipo Ligero, EPP)."
                "\n5. MANO DE OBRA / PERSONAL."
                "\n\nREGLAS IMPORTANTES:"
                "\n- Extrae UNICAMENTE la información presente en el texto."
                "\n- Si el usuario NO menciona algún dato, DEJA LOS CAMPOS VACÍOS o las listas vacías."
                "\n- NO INVENTES DATOS que no existen en la transcripción."
            )),
            ("human", "{input}")
        ])
        
        chain = prompt | structured_llm
        result = chain.invoke({"input": texto})
        return {"extraction": result, "error": ""}
        
    except Exception as e:
        return {"error": str(e), "extraction": None}

def llenar_pdf(datos: ExtractionSchema, template_file, output_buffer: io.BytesIO) -> bool:
    """
    Fills a PDF template with data.
    template_file: file-like object of the PDF template.
    output_buffer: BytesIO to write the result.
    """
    try:
        # Clone from the template file object
        reader = PdfReader(template_file)
        writer = PdfWriter()
        writer.append_pages_from_reader(reader)

        # IDs Mapping
        campos = {
            "Text-zMv1pANbT6": datos.folio,
            "Text-BWGpelBknd": datos.fecha,
            "Text-aIXySwB9KS": datos.cliente,
            "Text-nM4ed-cF7F": datos.requisitor,
            "Text-s_qiW_7PI_": datos.contacto,
            "Text-gWuPZ1KAe2": datos.fecha_entrega,
            "Paragraph-wbMnEjIT1Z": datos.actividad_programada,
            "Paragraph-WQ0uBD2HZa": datos.descripcion_generica,
            "Paragraph-fcK9vCRqcU": datos.total_general_materiales,
            "Paragraph-PhHxZHDsQM": datos.total_personas_cantidad
        }

        # IDs Cronograma
        ids_act = ["Paragraph-BpMGeNoYuM", "Paragraph-gpUeJG7MiI", "Paragraph-ppvGobsHJf", "Paragraph-x4Rxo-VMlF"]
        ids_time = ["Paragraph-0juE4mURqU", "Paragraph-o3-aor72Y9", "Paragraph-bFLVrhkHJR", "Paragraph-hnA3U7uFj9"]

        # IDs Materiales
        ids_mat_cant = ["Paragraph-mOc85rOV5v", "Paragraph-aZkNFhYsV0", "Paragraph-2KcNE5RQKm", "Paragraph-0YNxJfVihm"]
        ids_mat_uni  = ["Paragraph-QX95Jn6lL7", "Paragraph-W-Oe6E3Aky", "Paragraph-LdWc5odsE8", "Paragraph-qJJD1HJcmi"]
        ids_mat_desc = ["Paragraph-tniYDbExXq", "Paragraph-CDzQ8xQiY9", "Paragraph-K20bBl1g1u", "Paragraph-zxtIa6-K5a"]
        ids_mat_cost = ["Paragraph-vxHCYoz0SX", "Paragraph-9Fg0VLzK3B", "Paragraph-oIyrql9O-d", "Paragraph-o54QzxfUoz"]
        ids_mat_tot  = ["Paragraph-aR9dVQfgbE", "Paragraph-0X3g3JRBkP", "Paragraph-rVD_h6RRr8", "Paragraph-qI-q-EP-pO"]

        # IDs Recursos
        ids_herramienta = ["Paragraph-eoEEKrAXMZ", "Paragraph-1AXpmONEat", "Paragraph-1Up2zkuSRw", "Paragraph-UD340H3ODs"]
        ids_equipo_ligero = ["Paragraph-YzW23q5eHe", "Paragraph-weKF3TPoRL", "Paragraph-xXmhyP-Yw4", "Paragraph-gp2OIRtUa6"]
        ids_equipo_proteccion = ["Paragraph-dia-6q_uwG", "Paragraph-dhM0Conp3N", "Paragraph-xmMgIpH0sr", "Paragraph-CtylK4NC8d"]

        # IDs Personal
        ids_pers_num = ["Paragraph-gz1bF3j1gv", "Paragraph-5-V1XAInpN", "Paragraph-ePTToOXObF", "Paragraph-Kii2qNQflf"]
        ids_pers_cat = ["Paragraph-YZsw_vJ5gR", "Paragraph-TrNrFR1Evu", "Paragraph-YpLLxv4jqG", "Paragraph-MUeR9Wj3RK"]
        ids_pers_sal = ["Paragraph-2Umq0gbxOB", "Paragraph-JloBVq8QJE", "Paragraph-ZN8yyPHSY_", "Paragraph-Mfv_XwDUqt"]
        ids_pers_sem = ["Paragraph-rK6bbmiv5_", "Paragraph-dezCJ9KUKC", "Paragraph-NTVbHJppjW", "Paragraph-daR5W5zrmv"]
        ids_pers_net = ["Paragraph-GnY3FqtH_D", "Paragraph-75L_fbpfIc", "Paragraph-m0thOVI544", "Paragraph-gtojlJmtHp"]

        # Llenado Cronograma
        for i, item in enumerate(datos.programa_del_proyecto):
            if i < 4:
                campos[ids_act[i]] = f"• {item.descripcion}"
                campos[ids_time[i]] = item.tiempo

        # Llenado Materiales
        suma_materiales = 0.0
        for i, mat in enumerate(datos.lista_materiales):
            if i < 4:
                campos[ids_mat_cant[i]] = str(mat.cantidad)
                campos[ids_mat_uni[i]]  = str(mat.unidad)
                campos[ids_mat_desc[i]] = str(mat.descripcion)
                campos[ids_mat_cost[i]] = str(mat.costo)
                campos[ids_mat_tot[i]] = str(mat.total)
                
                # Assume total is already calculated correctly in the object
                try:
                    # Clean currency symbols for sum if needed, but data should come clean or pre-calculated
                    val = float(str(mat.total).replace('$','').replace(',',''))
                    suma_materiales += val
                except:
                    pass

        campos["Paragraph-fcK9vCRqcU"] = f"{suma_materiales:,.2f}"

        # Llenado Recursos
        for i, item in enumerate(datos.lista_herramientas):
            if i < 4: campos[ids_herramienta[i]] = f"• {item}"

        for i, item in enumerate(datos.lista_equipo_ligero):
            if i < 4: campos[ids_equipo_ligero[i]] = f"• {item}"

        for i, item in enumerate(datos.lista_equipo_proteccion):
            if i < 4: campos[ids_equipo_proteccion[i]] = f"• {item}"

        # Llenado Personal
        total_personas_count = 0
        for i, pers in enumerate(datos.lista_personal):
            if i < 4:
                campos[ids_pers_cat[i]] = str(pers.categoria)
                campos[ids_pers_sal[i]] = str(pers.salario_semanal)
                campos[ids_pers_sem[i]] = str(pers.semanas_cotizadas)
                campos[ids_pers_num[i]] = str(pers.cantidad_personas)
                campos[ids_pers_net[i]] = str(pers.salario_neto)

                try:
                    cant = float(pers.cantidad_personas)
                    total_personas_count += int(cant)
                except:
                    pass

        campos["Paragraph-PhHxZHDsQM"] = str(total_personas_count)

        # Update fields
        for page in writer.pages:
            writer.update_page_form_field_values(page, campos)

        # Handle checkbox/color logic if needed (simplified from original)
        # The original code sets background color for checkboxes based on job type.
        mapa_colores = {
            "Construcción": "Text-R_yKrCDlWu", "Remodelación": "Text-E3oPhuAo09",
            "Reparación": "Text-l_WfWo4uJC", "Mantenimiento": "Text-2I-6MjBd90",
            "Reconfiguración": "Text-7H8C5yi5RN", "Póliza": "Text-2Ddipy5msq",
            "Inspección": "Text-HWEOklKxRk"
        }
        id_color = mapa_colores.get(datos.tipo_de_trabajo)
        
        # This part is a bit tricky with pypdf and might need exact field names.
        # We'll attempt to replicate the logic if possible, but might skip if too complex for now.
        # Original code iterates annotations.
        if "/Annots" in writer.pages[0]:
            for annot in writer.pages[0]["/Annots"]:
                obj = annot.get_object()
                nm = obj.get("/T")
                if nm == "Paragraph-wbMnEjIT1Z" or (id_color and nm == id_color):
                    if "/MK" not in obj: obj[NameObject("/MK")] = DictionaryObject()
                    obj["/MK"][NameObject("/BG")] = ArrayObject([FloatObject(1), FloatObject(1), FloatObject(0)]) # Yellow
                    if "/AP" in obj: del obj["/AP"]

        if "/AcroForm" not in writer.root_object:
             writer.root_object[NameObject("/AcroForm")] = DictionaryObject()
        writer.root_object["/AcroForm"][NameObject("/NeedAppearances")] = BooleanObject(True)

        writer.write(output_buffer)
        return True

    except Exception as e:
        print(f"Error filling PDF: {e}")
        return False

def enviar_correos(datos: ExtractionSchema, sender_email: str, password: str, dests: List[str]):
    """
    Sends emails with the report.
    dests: List of 3 emails [dest1, dest2, dest3]
    """
    if len(dests) < 3:
        return "Error: Se requieren 3 destinatarios."

    destinatario_1, destinatario_2, destinatario_3 = dests[0], dests[1], dests[2]

    # CUERPO CORREO 1
    body_1 = f"""
    [REPORTE 1] DATOS EXTRAIDOS Y LISTAS CRUDAS

    --- # IDs Generales (Datos del Proyecto) ---
    Folio: {datos.folio}
    Fecha: {datos.fecha}
    Cliente: {datos.cliente}
    Requisitor: {datos.requisitor}
    Contacto: {datos.contacto}
    Fecha Entrega: {datos.fecha_entrega}
    Actividad Prog: {datos.actividad_programada}
    Tipo Trabajo: {datos.tipo_de_trabajo}
    Descripción: {datos.descripcion_generica}

    --- # IDs Cronograma (Actividades Detectadas) ---
    """
    for act in datos.programa_del_proyecto:
        body_1 += f"- {act.descripcion} (Tiempo: {act.tiempo})\n"

    body_1 += "\n    --- # IDs Materiales (Lista Detectada) ---\n"
    for mat in datos.lista_materiales:
        body_1 += f"- {mat.descripcion} | Cant: {mat.cantidad} {mat.unidad} | Costo: {mat.costo}\n"

    # CUERPO CORREO 2
    body_2 = f"""
    [REPORTE 2] RECURSOS, PERSONAL Y CRONOGRAMA FORMATEADO

    --- # IDs Recursos (Listas de Herramientas/Equipo) ---
    > Herramientas: {', '.join(datos.lista_herramientas)}
    > Eq. Ligero: {', '.join(datos.lista_equipo_ligero)}
    > EPP: {', '.join(datos.lista_equipo_proteccion)}

    --- # IDs Personal (Datos Crudos) ---
    """
    for p in datos.lista_personal:
        body_2 += f"- Categoria: {p.categoria}, Cant: {p.cantidad_personas}, Sem: {p.semanas_cotizadas}, Sal: {p.salario_semanal}\n"

    body_2 += "\n    --- # Llenado Cronograma (Formato PDF) ---\n"
    for i, act in enumerate(datos.programa_del_proyecto):
        if i < 4:
            body_2 += f"Paso {i+1}: • {act.descripcion} [Duración: {act.tiempo}]\n"

    # CUERPO CORREO 3
    body_3 = f"""
    [REPORTE 3] DETALLES FINANCIEROS Y DE LLENADO

    --- # Llenado Materiales (Cálculos y Totales) ---
    """
    suma_m = 0.0
    for mat in datos.lista_materiales:
        try:
            p = float(str(mat.costo).replace('$','').replace(',',''))
            c = float(str(mat.cantidad).replace(',',''))
            t = p * c
            suma_m += t
            body_3 += f"Material: {mat.descripcion} -> Total Línea: ${t:,.2f}\n"
        except:
            body_3 += f"Material: {mat.descripcion} -> Error cálculo\n"
    body_3 += f"TOTAL MATERIALES: ${suma_m:,.2f}\n"

    body_3 += "\n    --- # Llenado Recursos (Formato PDF) ---\n"
    body_3 += f"Listado Herramientas: • {' • '.join(datos.lista_herramientas[:4])}\n"
    body_3 += f"Listado Eq. Ligero:   • {' • '.join(datos.lista_equipo_ligero[:4])}\n"
    body_3 += f"Listado EPP:          • {' • '.join(datos.lista_equipo_proteccion[:4])}\n"

    body_3 += "\n    --- # Llenado Personal (Cálculo Nómina) ---\n"
    total_pers = 0
    for p in datos.lista_personal:
        try:
            c = float(p.cantidad_personas)
            sal = float(str(p.salario_semanal).replace('$','').replace(',',''))
            sem = float(p.semanas_cotizadas)
            neto = c * sal * sem
            total_pers += int(c)
            body_3 += f"Personal: {p.categoria} (x{int(c)}) -> Costo Total: ${neto:,.2f}\n"
        except:
            pass
    body_3 += f"TOTAL PERSONAS: {total_pers}"

    context = ssl.create_default_context()

    try:
        with smtplib.SMTP_SSL("smtp.gmail.com", 465, context=context) as smtp:
            smtp.login(sender_email, password)

            # Enviar Correo 1
            msg1 = EmailMessage()
            msg1["From"] = sender_email
            msg1["To"] = destinatario_1
            msg1["Subject"] = "Reporte 1: Datos Generales, Cronograma, Materiales"
            msg1.set_content(body_1)
            smtp.send_message(msg1)

            # Enviar Correo 2
            msg2 = EmailMessage()
            msg2["From"] = sender_email
            msg2["To"] = destinatario_2
            msg2["Subject"] = "Reporte 2: Recursos, Personal, Llenado Cronograma"
            msg2.set_content(body_2)
            smtp.send_message(msg2)

            # Enviar Correo 3
            msg3 = EmailMessage()
            msg3["From"] = sender_email
            msg3["To"] = destinatario_3
            msg3["Subject"] = "Reporte 3: Llenado de Materiales, Recursos y Personal"
            msg3.set_content(body_3)
            smtp.send_message(msg3)

        return "EXITO: Se han enviado los 3 correos correctamente."

    except Exception as e:
        return f"ERROR enviando correos: {e}"
