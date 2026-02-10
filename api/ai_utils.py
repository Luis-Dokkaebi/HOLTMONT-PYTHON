import os
import io
from datetime import datetime
from typing import List, TypedDict, Optional
from pydantic import BaseModel, Field

try:
    from groq import Groq
except ImportError:
    Groq = None

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
    tiempo: str = Field(default="", description="Duración estimada (Sugerida por IA si no se menciona).")
    costo_estimado: str = Field(default="", description="Costo estimado de mano de obra para esta actividad (Sugerido).")

class ItemHerramienta(BaseModel):
    descripcion: str = Field(default="", description="Descripción de la herramienta.")
    costo: str = Field(default="", description="Costo estimado si aplica.")
    cantidad: str = Field(default="1", description="Cantidad.")

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
        max_length=10
    )

    # CHECKLIST EHS (NUEVO: Sugerencias de Seguridad)
    checklist_ehs: List[str] = Field(
        default_factory=list,
        description="Lista de requerimientos de seguridad detectados (ej: 'Arnés', 'Permiso de Fuego', 'Extintor', 'Línea de Vida')."
    )
    riesgos_detectados: List[str] = Field(
        default_factory=list,
        description="Lista de riesgos potenciales inferidos (ej: 'Caída de altura', 'Proyección de partículas')."
    )

    # LISTAS DE RECURSOS (Modified to include struct for tool mapping if needed, but simple strings work for now)
    # The frontend expects tools with quantity, cost, etc.
    # Let's try to extract structured tools if possible, or mapping strings.
    # We will stick to string lists as per original prompt logic but maybe enhance if needed.
    # Original prompt had simple lists. Let's keep extraction consistent.
    lista_herramientas: List[str] = Field(
        default_factory=list,
        description="Lista de herramientas requeridas. (Sugiere si faltan obvias)",
        max_length=10
    )
    lista_equipo_ligero: List[str] = Field(
        default_factory=list,
        description="Lista de equipo ligero.",
        max_length=5
    )
    lista_equipo_proteccion: List[str] = Field(
        default_factory=list,
        description="Lista de EPP (Cascos, guantes, etc). Sugiere basado en la tarea.",
        max_length=5
    )

    # LISTA DE PERSONAL
    lista_personal: List[ItemPersonal] = Field(
        default_factory=list,
        description="Desglose de mano de obra (Puesto, Salario, Semanas).",
        max_length=5
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

# --- FUNCTIONS ---

def transcribir_audio(api_key: str, audio_file_content: bytes, filename: str = "audio.wav") -> str:
    """
    Transcribes audio using Groq API.
    audio_file_content: bytes of the audio file.
    """
    if not api_key:
        return "Error: Falta GROQ_API_KEY."

    try:
        client = Groq(api_key=api_key)

        # Use a BytesIO object with a name attribute
        file_obj = io.BytesIO(audio_file_content)
        file_obj.name = filename

        transcription = client.audio.transcriptions.create(
            file=(filename, file_obj.read()),
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
                f"Hoy es {fecha_actual}. Eres un ingeniero experto en costos, proyectos y seguridad industrial (EHS)."
                "\n\nTU TAREA ES EXTRAER E INFERIR:"
                "\n1. Datos del Cliente y Proyecto."
                "\n2. Cronograma de actividades (ESTIMA tiempos si no se mencionan, basado en rendimientos estándar)."
                "\n3. Lista de Materiales (con precios y totales)."
                "\n4. Recursos (Herramientas, Equipo Ligero, EPP)."
                "\n5. MANO DE OBRA / PERSONAL (Estima costos si no se dan)."
                "\n6. SEGURIDAD (EHS): Analiza la descripción para detectar riesgos (Altura, Caliente, Confinado) y SUGIERE el EPP y permisos necesarios en 'checklist_ehs'."
                "\n\nREGLAS IMPORTANTES:"
                "\n- Prioriza la información explícita del usuario."
                "\n- SI FALTA INFORMACIÓN TÉCNICA (tiempos, costos, seguridad): USA TU CONOCIMIENTO DE INGENIERÍA para sugerir valores realistas."
                "\n- Si el trabajo implica altura (>1.8m), soldadura o electricidad, OBLIGATORIAMENTE sugiere el EPP correspondiente (Arnés, Careta, Dielectrico)."
            )),
            ("human", "{input}")
        ])

        chain = prompt | structured_llm
        result = chain.invoke({"input": texto})
        return {"extraction": result.dict(), "error": ""}

    except Exception as e:
        return {"error": str(e), "extraction": None}
