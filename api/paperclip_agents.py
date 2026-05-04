import os
from typing import TypedDict
import json
try:
    from langchain_groq import ChatGroq
    from langchain_core.prompts import ChatPromptTemplate
    from langgraph.graph import StateGraph, START, END
except ImportError:
    ChatGroq = None

# --- STATE DEFINITION ---
class PaperclipState(TypedDict):
    user_request: str
    levantamiento_data: str
    calculo_data: str
    precios_data: str

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

# --- GRAPH BUILDER ---
def build_paperclip_graph(llm):
    builder = StateGraph(PaperclipState)

    builder.add_node("levantamiento", lambda state: levantamiento_node(state, llm))
    builder.add_node("calculo", lambda state: calculo_node(state, llm))
    builder.add_node("precios", lambda state: precios_node(state, llm))

    builder.add_edge(START, "levantamiento")
    builder.add_edge("levantamiento", "calculo")
    builder.add_edge("calculo", "precios")
    builder.add_edge("precios", END)

    return builder.compile()

# --- MAIN EXECUTION LOGIC ---
def run_paperclip_agency(user_request: str, api_key: str = None) -> dict:
    groq_api_key = api_key or os.environ.get("GROQ_API_KEY")
    if not groq_api_key:
        return {"success": False, "error": "Falta GROQ_API_KEY en el entorno"}

    if ChatGroq is None:
        return {"success": False, "error": "Falta la librería langchain_groq"}

    llm = ChatGroq(model="llama-3.3-70b-versatile", temperature=0.2, api_key=groq_api_key)
    graph = build_paperclip_graph(llm)

    initial_state = {
        "user_request": user_request,
        "levantamiento_data": "",
        "calculo_data": "",
        "precios_data": ""
    }

    try:
        final_state = graph.invoke(initial_state)
        return {
            "success": True,
            "levantamiento": final_state.get("levantamiento_data", ""),
            "calculo": final_state.get("calculo_data", ""),
            "precios": final_state.get("precios_data", "")
        }
    except Exception as e:
        return {"success": False, "error": f"Error ejecutando la agencia: {str(e)}"}
