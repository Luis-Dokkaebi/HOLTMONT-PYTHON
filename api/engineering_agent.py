import os
import io
import operator
from typing import List, Literal
from typing_extensions import Annotated, TypedDict

from pydantic import BaseModel, Field

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
    from langchain_community.tools.tavily_search import TavilySearchResults
    from langchain_core.prompts import ChatPromptTemplate
    from langgraph.graph import StateGraph, START, END
except ImportError:
    ChatGroq = None


# --- CONFIGURATION ---
MAX_ITERATIONS = 2

# --- DATA MODELS ---

class GraphState(TypedDict):
    user_request: str
    draft_questions: str
    critique: str
    search_queries: List[str]
    research_context: Annotated[str, operator.add]
    iteration: int
    is_approved: bool

class EvaluatorOutput(BaseModel):
    is_approved: bool = Field(description="True si las preguntas cubren todos los aspectos técnicos necesarios. False en caso contrario.")
    critique: str = Field(description="Crítica detallada de lo que falta o está mal en las preguntas actuales.")
    search_queries: List[str] = Field(description="Lista de búsquedas (máx 2) para Google si se requiere investigar normativas o estándares de construcción. Vacío si no es necesario.")


# --- NODE FUNCTIONS ---

def interviewer_node(state: GraphState, llm) -> dict:
    iteracion_actual = state.get('iteration', 0) + 1
    print(f"\n--- [Agente Entrevistador] Generando Borrador (Iteración {iteracion_actual}) ---")

    prompt = ChatPromptTemplate.from_messages([
        ("system", """Eres un Ingeniero Civil Arquitecto experto. Tu objetivo es generar una lista exhaustiva de preguntas para un cliente que solicita una cotización.

        Contexto de investigación disponible: {research_context}

        Crítica del revisor (si existe): {critique}

        Usa la crítica y la investigación para refinar tus preguntas. Entrega SOLO la lista de preguntas, organizada por categorías (ej. Topografía, Materiales, Legal)."""),
        ("human", "Solicitud original del cliente: {user_request}\n\nPreguntas actuales: {draft_questions}")
    ])

    chain = prompt | llm

    response = chain.invoke({
        "user_request": state["user_request"],
        "draft_questions": state.get("draft_questions", "Ninguna todavía."),
        "critique": state.get("critique", "Ninguna todavía."),
        "research_context": state.get("research_context", "Sin investigación previa.")
    })

    return {
        "draft_questions": response.content,
        "iteration": iteracion_actual
    }

def evaluator_node(state: GraphState, llm) -> dict:
    print("\n--- [Agente Evaluador] Reflexionando sobre las preguntas ---")

    prompt = ChatPromptTemplate.from_messages([
        ("system", """Eres un Revisor Senior de Proyectos de Construcción. Analiza la lista de preguntas generada.
        Asegúrate de que no falte preguntar sobre: normativas locales de uso de suelo, tipo de terreno, acceso de maquinaria pesada, servicios básicos existentes, etc.
        Sé muy crítico. Si las preguntas son muy superficiales, recházalas (is_approved=False).
        Si necesitas saber sobre una norma actual para pedirle el dato exacto al cliente, genera un 'search_queries'."""),
        ("human", "Solicitud del cliente: {user_request}\n\nPreguntas generadas: {draft_questions}")
    ])

    evaluator_llm = llm.with_structured_output(EvaluatorOutput)
    chain = prompt | evaluator_llm

    result: EvaluatorOutput = chain.invoke({
        "user_request": state["user_request"],
        "draft_questions": state["draft_questions"]
    })

    print(f"  -> Aprobado: {result.is_approved}")
    print(f"  -> Crítica: {result.critique[:150]}...")

    return {
        "is_approved": result.is_approved,
        "critique": result.critique,
        "search_queries": result.search_queries
    }

def research_node(state: GraphState, tavily_tool) -> dict:
    print("\n--- [Herramienta Web] Buscando Normativas/Contexto ---")
    queries = state.get("search_queries", [])
    new_context = ""

    for q in queries:
        print(f"  -> Buscando: {q}")
        try:
            docs = tavily_tool.invoke({"query": q})
            for doc in docs:
                new_context += f"- Fuente: {doc.get('url', 'N/A')}\nContenido: {doc.get('content', '')}\n\n"
        except Exception as e:
            print(f"  -> Error buscando {q}: {e}")

    return {"research_context": new_context}

def route_after_evaluation(state: GraphState) -> Literal["research_node", "interviewer_node", "END"]:
    if state["is_approved"] or state["iteration"] >= MAX_ITERATIONS:
        print("\n--- FLUJO TERMINADO ---")
        return "END"
    elif len(state.get("search_queries", [])) > 0:
        return "research_node"
    else:
        return "interviewer_node"

def build_graph(llm, tavily_tool):
    builder = StateGraph(GraphState)

    builder.add_node("interviewer_node", lambda state: interviewer_node(state, llm))
    builder.add_node("evaluator_node", lambda state: evaluator_node(state, llm))
    builder.add_node("research_node", lambda state: research_node(state, tavily_tool))

    builder.add_edge(START, "interviewer_node")
    builder.add_edge("interviewer_node", "evaluator_node")

    builder.add_conditional_edges(
        "evaluator_node",
        route_after_evaluation,
        {
            "research_node": "research_node",
            "interviewer_node": "interviewer_node",
            "END": END
        }
    )

    builder.add_edge("research_node", "interviewer_node")
    return builder.compile()

# --- MAIN AUDIO PROCESSING LOGIC ---

def transcribir_con_groq(api_key: str, audio_file_content: bytes, filename: str = "audio.wav") -> str:
    """
    Transcribes audio using Groq API.
    """
    if Groq is None:
        return "Error: La librería 'groq' no está instalada."

    if not api_key:
        return "Error: Falta GROQ_API_KEY."

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
            out, err = process.communicate(input=audio_file_content)

            if process.returncode == 0:
                audio_file_content = out
                filename = "converted_audio.wav"
            else:
                print(f"FFmpeg warning: {err.decode('utf-8') if err else 'Unknown error'}")
        except Exception as e:
            print(f"FFmpeg error: {e}")
            # Continue with original content

    try:
        client = Groq(api_key=api_key)
        transcription = client.audio.transcriptions.create(
            file=(filename, audio_file_content),
            model="whisper-large-v3",
            response_format="json",
            language="es",
            temperature=0.0
        )
        return transcription.text
    except Exception as e:
        return f"Error en transcripción: {str(e)}"

def process_audio(audio_bytes: bytes, filename: str = "audio.wav") -> dict:
    """
    1. Transcribes audio bytes to text
    2. Runs the engineering multi-agent LangGraph workflow
    3. Returns both transcription and draft questions
    """
    groq_api_key = os.environ.get("API_KEY_GROQ")
    tavily_api_key = os.environ.get("API_KEY_TAVILY")

    if not groq_api_key:
        return {"success": False, "message": "Falta GROQ_API_KEY en el entorno"}

    # 1. Transcribe
    transcription = transcribir_con_groq(groq_api_key, audio_bytes, filename)
    if "Error" in transcription:
         return {"success": False, "message": transcription}

    # 2. Setup Graph
    if ChatGroq is None:
        return {"success": False, "message": "Falta langchain_groq"}

    llm = ChatGroq(model="llama-3.3-70b-versatile", temperature=0.2, api_key=groq_api_key)

    # If tavily is not configured, we'll use a dummy or skip
    tavily_tool = None
    if tavily_api_key:
        tavily_tool = TavilySearchResults(max_results=2, api_key=tavily_api_key)
    else:
        # Dummy tool that returns nothing if missing API key
        class DummyTavily:
            def invoke(self, *args, **kwargs):
                return [{"url": "N/A", "content": "Sin TAVILY_API_KEY, no se puede buscar."}]
        tavily_tool = DummyTavily()

    graph = build_graph(llm, tavily_tool)

    # 3. Invoke Graph
    initial_state = {
        "user_request": transcription,
        "iteration": 0,
        "research_context": ""
    }

    try:
        final_state = graph.invoke(initial_state, config={"recursion_limit": 15})
        draft_questions = final_state.get("draft_questions", "No se generaron preguntas.")
        return {
            "success": True,
            "transcription": transcription,
            "questions": draft_questions
        }
    except Exception as e:
        return {"success": False, "message": f"Error ejecutando LangGraph: {str(e)}"}
