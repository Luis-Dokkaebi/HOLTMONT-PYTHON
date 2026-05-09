import os
import json
from typing import TypedDict, List
from pydantic import BaseModel, Field

try:
    from langchain_groq import ChatGroq
    from langchain_core.prompts import ChatPromptTemplate
    from langgraph.graph import StateGraph, START, END
except ImportError:
    ChatGroq = None

try:
    from langchain_google_genai import ChatGoogleGenerativeAI
except ImportError:
    ChatGoogleGenerativeAI = None

# --- PYDANTIC SCHEMAS FOR STRUCTURED EXTRACTION ---
class LaborItem(BaseModel):
    category: str = Field(description="Rol o puesto de la persona (Ej. Operario, Ingeniero, Albañil)")
    personnel: str = Field(description="Cantidad de personas requeridas con este rol")
    unit: str = Field(description="Unidad de tiempo a contratar (debe ser: 'hora', 'dia', o 'semana')")
    weeks: str = Field(description="Duración o cantidad de la unidad de tiempo (Ej. 3, 5, 10)")
    salary: str = Field(description="Salario o costo unitario estimado por la unidad de tiempo")

class MaterialItem(BaseModel):
    description: str = Field(description="Descripción clara del material o insumo")
    unit: str = Field(description="Unidad de medida (Ej. pza, bulto, m2, m3, lote)")
    quantity: str = Field(description="Cantidad estimada a utilizar")
    cost: str = Field(description="Costo unitario estimado del material")

class ToolItem(BaseModel):
    description: str = Field(description="Descripción de la herramienta requerida")
    unit: str = Field(description="Unidad de medida (Ej. pza, lote)")
    quantity: str = Field(description="Cantidad estimada")
    cost: str = Field(description="Costo estimado")

class EquipmentItem(BaseModel):
    description: str = Field(description="Descripción del equipo especial, maquinaria o accesorio")
    unit: str = Field(description="Unidad de medida (Ej. hora, dia, unidad)")
    quantity: str = Field(description="Cantidad de equipos")
    days: str = Field(description="Días estimados de uso o renta")
    cost: str = Field(description="Costo unitario o de renta estimado")

class TravelItem(BaseModel):
    concepto: str = Field(description="Concepto del viático (Ej. Hotel, Casetas, Comidas)")
    cantidad: str = Field(description="Cantidad de noches, comidas o viajes")
    costo_unitario: str = Field(description="Costo unitario estimado")

class StructuredAgencyData(BaseModel):
    laborTable: List[LaborItem] = Field(description="Lista estructurada de mano de obra estimada")
    requiredMaterials: List[MaterialItem] = Field(description="Lista estructurada de materiales e insumos estimados")
    toolsRequired: List[ToolItem] = Field(description="Lista de herramientas menores requeridas")
    specialEquipment: List[EquipmentItem] = Field(description="Lista de maquinaria y equipo especial requerido")
    viaticosTable: List[TravelItem] = Field(description="Lista de viáticos requeridos si aplica")

# --- STATE DEFINITION ---
class PaperclipState(TypedDict):
    user_request: str
    levantamiento_data: str
    architect_data: str
    calculo_data: str
    precios_data: str
    structured_data: str

# --- NODES ---
def levantamiento_node(state: PaperclipState, llm) -> dict:
    """Agente 1: Levantamiento. Extrae el alcance y condiciones del sitio."""
    print("--- [Agente de Levantamiento] Analizando requerimientos ---")
    
    prompt = ChatPromptTemplate.from_messages([
        ("system", "Eres un Ingeniero Topógrafo y Residente de Obra experto. Tu objetivo es analizar la solicitud del cliente y generar un reporte de levantamiento claro y estructurado. Extrae: 1) Condiciones del sitio, 2) Alcance del trabajo a realizar, 3) Posibles restricciones técnicas o información faltante. Presenta la información en un formato claro."),
        ("human", "Solicitud del cliente: {user_request}")
    ])
    
    chain = prompt | llm
    response = chain.invoke({"user_request": state["user_request"]})
    
    return {"levantamiento_data": response.content}

def architect_node(state: PaperclipState, llm) -> dict:
    """Agente Arquitecto: Genera el código JSON base para el Pascal Editor 3D."""
    print("--- [Agente Arquitecto 3D] Generando modelo volumétrico ---")
    
    prompt = ChatPromptTemplate.from_messages([
        ("system", "Eres un Arquitecto de Software 3D. Tu objetivo es leer el reporte de levantamiento y generar un JSON válido que represente la volumetría básica del proyecto. El JSON debe contener un arreglo de 'walls' (paredes) con coordenadas X, Y. Usa valores numéricos coherentes basados en los metros solicitados. Si no hay medidas, asume una habitación de 4x4. Entrega SOLO el JSON, sin bloques de código ni texto adicional."),
        ("human", "Reporte de Levantamiento:\n{levantamiento_data}")
    ])
    
    chain = prompt | llm
    response = chain.invoke({"levantamiento_data": state["levantamiento_data"]})
    
    content = response.content.strip()
    if content.startswith("```json"): content = content[7:]
    elif content.startswith("```"): content = content[3:]
    if content.endswith("```"): content = content[:-3]
    
    content = content.strip()

    try:
        import json
        # Ensure it is parseable JSON.
        parsed = json.loads(content)
        # Re-dump to ensure it is a clean string
        return {"architect_data": json.dumps(parsed)}
    except Exception as e:
        print(f"Error parsing architect JSON: {e}, Content: {content}")
        # Default simple room for Pascal Editor fallback
        default_room = {
            "state": {
                "nodes": [
                    {"id": "n1", "type": "wall", "position": {"x": -2, "y": -2, "z": 0}},
                    {"id": "n2", "type": "wall", "position": {"x": 2, "y": -2, "z": 0}},
                    {"id": "n3", "type": "wall", "position": {"x": 2, "y": 2, "z": 0}},
                    {"id": "n4", "type": "wall", "position": {"x": -2, "y": 2, "z": 0}}
                ]
            }
        }
        import json
        return {"architect_data": json.dumps(default_room)}

def calculo_node(state: PaperclipState, llm) -> dict:
    """Agente 2: Cálculo y Diseño. Genera requerimientos técnicos basados en el levantamiento."""
    print("--- [Agente de Cálculo y Diseño] Diseñando solución técnica ---")
    
    prompt = ChatPromptTemplate.from_messages([
        ("system", "Eres un Ingeniero Calculista y Arquitecto experto. Tu objetivo es tomar el reporte de levantamiento y generar los requerimientos técnicos para la obra. Debes detallar: 1) Catálogo de conceptos principales, 2) Lista estimada de materiales con cantidades, 3) Mano de obra requerida, 4) Maquinaria y equipo especial."),
        ("human", "Reporte de Levantamiento:\n{levantamiento_data}")
    ])
    
    chain = prompt | llm
    response = chain.invoke({"levantamiento_data": state["levantamiento_data"]})
    
    return {"calculo_data": response.content}

def precios_node(state: PaperclipState, llm) -> dict:
    """Agente 3: Precios Unitarios. Estima costos basados en el cálculo y diseño."""
    print("--- [Agente de Precios Unitarios] Estimando presupuesto ---")
    
    prompt = ChatPromptTemplate.from_messages([
        ("system", "Eres un Analista de Precios Unitarios experto. Tu objetivo es tomar los requerimientos técnicos y de materiales, y generar una estimación de presupuesto aproximada. Genera un desglose que incluya: 1) Costo estimado de materiales, 2) Costo estimado de mano de obra, 3) Costos de equipo, 4) Total estimado del proyecto. Debes presentar esto de manera profesional."),
        ("human", "Requerimientos Técnicos (Cálculo y Diseño):\n{calculo_data}")
    ])
    
    chain = prompt | llm
    response = chain.invoke({"calculo_data": state["calculo_data"]})
    
    return {"precios_data": response.content}

def integrador_node(state: PaperclipState, llm) -> dict:
    """Agente 4: Integrador. Extrae los recursos en formato JSON estricto."""
    print("--- [Agente Integrador] Estructurando JSON ---")
    
    prompt = ChatPromptTemplate.from_messages([
        ("system", "Eres un Analista de Datos experto. Extrae la mano de obra, materiales, equipos y herramientas de los reportes anteriores en el formato JSON estricto solicitado. Extrae explícitamente los costos unitarios, salarios y cantidades basándote en el reporte de 'Precios'. NUNCA dejes cantidades o costos en 0 a menos que el texto diga explícitamente que es gratis."),
        ("human", "Cálculo y Diseño:\n{calculo}\n\nPrecios:\n{precios}")
    ])
    
    # Use structured output
    structured_llm = llm.with_structured_output(StructuredAgencyData)
    chain = prompt | structured_llm
    
    try:
        import json
        result: StructuredAgencyData = chain.invoke({
            "calculo": state["calculo_data"],
            "precios": state["precios_data"]
        })
        json_dict = result.model_dump()
        json_dict["arquitectura_3d_json"] = state.get("architect_data", "")
        return {"structured_data": json.dumps(json_dict)}
    except Exception as e:
        import json
        print(f"Error en extracción estructurada: {e}")
        empty_data = StructuredAgencyData(laborTable=[], requiredMaterials=[], toolsRequired=[], specialEquipment=[], viaticosTable=[])
        empty_dict = empty_data.model_dump()
        empty_dict["arquitectura_3d_json"] = ""
        return {"structured_data": json.dumps(empty_dict)}

# --- GRAPH BUILDER ---
def build_paperclip_graph(llm_text, llm_structured):
    builder = StateGraph(PaperclipState)
    
    # Text agents use llm_text (e.g. Gemini)
    builder.add_node("levantamiento", lambda state: levantamiento_node(state, llm_text))
    builder.add_node("calculo", lambda state: calculo_node(state, llm_text))
    builder.add_node("precios", lambda state: precios_node(state, llm_text))
    
    # Formatting/Structured agents use llm_structured (e.g. Groq)
    builder.add_node("architect", lambda state: architect_node(state, llm_structured))
    builder.add_node("integrador", lambda state: integrador_node(state, llm_structured))
    
    builder.add_edge(START, "levantamiento")
    builder.add_edge("levantamiento", "architect")
    builder.add_edge("architect", "calculo")
    builder.add_edge("calculo", "precios")
    builder.add_edge("precios", "integrador")
    builder.add_edge("integrador", END)
    
    return builder.compile()

# --- MAIN EXECUTION LOGIC ---
def run_paperclip_agency(user_request: str, api_key: str = None) -> dict:
    groq_api_key = api_key or os.environ.get("GROQ_API_KEY")
    gemini_key = os.environ.get("GEMINI_API_KEY")
    
    if not groq_api_key:
        return {"success": False, "error": "Falta GROQ_API_KEY en el entorno"}
    
    if ChatGroq is None:
        return {"success": False, "error": "Falta la librería langchain_groq o langchain_google_genai"}

    # Groq is strictly used for JSON formatting / Tool calling (Structured Outputs)
    llm_structured = ChatGroq(model="llama-3.3-70b-versatile", temperature=0.2, api_key=groq_api_key)
    
    # Use Gemini for heavy text processing to save tokens. Fallback to Groq if missing.
    if gemini_key and ChatGoogleGenerativeAI is not None:
        llm_text = ChatGoogleGenerativeAI(model="gemini-1.5-pro", temperature=0.3, google_api_key=gemini_key)
    else:
        print("Aviso: GEMINI_API_KEY no detectada. Usando Groq para todos los agentes.")
        llm_text = llm_structured

    graph = build_paperclip_graph(llm_text, llm_structured)
    
    initial_state = {
        "user_request": user_request,
        "levantamiento_data": "",
        "architect_data": "",
        "calculo_data": "",
        "precios_data": "",
        "structured_data": ""
    }
    
    try:
        final_state = graph.invoke(initial_state)
        return {
            "success": True,
            "levantamiento": final_state.get("levantamiento_data", ""),
            "calculo": final_state.get("calculo_data", ""),
            "precios": final_state.get("precios_data", ""),
            "structured_data": final_state.get("structured_data", "{}")
        }
    except Exception as e:
        return {"success": False, "error": f"Error ejecutando la agencia: {str(e)}"}
