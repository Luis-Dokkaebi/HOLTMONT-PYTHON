"""
El agente de prospección: lee el sitio del negocio y redacta, o redacta a ciegas.

Es el grafo de la celda 4 del notebook (`modelo_analisis_geoespacial.ipynb`)
portado a la plataforma. La forma es la misma —mirar si hay sitio, leerlo,
analizarlo o redactar el contacto— y cambian tres cosas, todas por una razón
medida:

1. **La clave de Groq sale del servidor.** El notebook la pide en un
   `widgets.Password` y, peor, tiene una clave real escrita en un comentario al
   final de la celda. Aquí sale de `GROQ_API_KEY`, igual que en `api/ai_utils.py`.
   La clave **nunca** baja al navegador (plan §4, decisión D5).

2. **`check_website` pasa de dos ramas a tres estados.** El notebook solo
   distinguía "tiene web" de "no tiene". Aquí el texto puede venir de la caché
   precalculada, de una lectura en vivo o de Tavily, y de dónde vino se declara
   en la respuesta (`fuente`). No es un detalle: quien firma un correo tiene
   derecho a saber si el agente leyó la página de ayer o el resumen de un
   buscador.

3. **El scraping no corre aquí.** `crawl4ai` + Playwright no caben en el bundle
   de Vercel, y esperar 5–30 s a que responda un sitio ajeno con el vendedor
   mirando la pantalla no es una interfaz. Tres capas, en orden de costo
   (plan §4, decisión D3):

       caché precalculada  ->  fetch en vivo (biblioteca estándar)  ->  Tavily

   La primera la llena un job fuera de línea; la segunda está medida en §2.3; la
   tercera cubre justo el caso que la segunda no puede —las páginas que arman su
   contenido con JavaScript—.

Todo lo de fuera se **inyecta**: el LLM, el extractor, el buscador y la caché.
Es el mismo patrón de `api/services/plano.py` con `llm_disponible()`, y es lo que
permite que las pruebas ejerzan el grafo entero sin red, sin clave y sin base.

**El 13.6%.** Solo 2,848 de los 20,957 establecimientos declararon sitio web. La
rama que lee páginas se activa en uno de cada siete casos; las otras seis veces
el grafo va directo a redactar. La rama de redacción no es el caso raro: es el
caso normal.
"""

from __future__ import annotations

import os
from typing import Any, Callable, Dict, Optional, TypedDict

# Los tres orígenes posibles del texto, más la ausencia. Van al contrato
# (`fuente` en la respuesta) porque distinguen un análisis fundado de una
# conjetura.
FUENTE_CACHE = "cache"
FUENTE_WEB = "web"
FUENTE_TAVILY = "tavily"
FUENTE_SIN_WEB = "sin_web"

TIPO_ANALISIS = "analisis"
TIPO_CORREO = "correo"

MODELO = "llama-3.3-70b-versatile"

# Recorte del texto que se le manda al LLM. 400 KB de HTML convertido a texto no
# caben en la ventana de contexto y no hacen falta: lo que describe a un negocio
# está en la portada.
TECHO_CONTEXTO_CHARS = 6000

PROMPT_ANALISIS = """Eres analista de compras de una constructora en la Ciudad de México.

Del sitio de este negocio, di en español y en no más de 120 palabras:
- a qué se dedica realmente,
- qué de su catálogo le sirve a una constructora,
- una señal de si es proveedor serio o no.

Si el texto no alcanza para responder algo, dilo en vez de inventarlo.

NEGOCIO: {nombre}
GIRO SEGÚN EL INEGI: {giro}
LO QUE SE PREGUNTA: {consulta}

TEXTO DE SU SITIO:
{texto}"""

PROMPT_CORREO = """Eres del área de compras de una constructora en la Ciudad de México.

Redacta en español un correo BREVE (máximo 120 palabras) pidiendo cotización a
este negocio. Trato de usted, sin adjetivos de venta, y di con claridad qué se
necesita. No inventes datos del negocio que no estén abajo.

Devuelve solo el cuerpo del correo, sin asunto y sin firma.

NEGOCIO: {nombre}
GIRO SEGÚN EL INEGI: {giro}
ALCALDÍA: {alcaldia}
LO QUE SE NECESITA: {consulta}
{contexto}"""


class EstadoProspeccion(TypedDict, total=False):
    """
    La pizarra del grafo. Un `TypedDict` y no un `dict` pelado, y no es estilo:
    LangGraph crea un canal por clave declarada y **fusiona** lo que devuelve
    cada nodo. Con `StateGraph(dict)` el valor de retorno de un nodo REEMPLAZA
    el estado entero, así que `fuente` —que escribe el nodo del sitio— se perdía
    en cuanto corría el de redacción, y la respuesta decía `sin_web` para un
    texto que venía de la caché. Falla en silencio: el análisis sale bien y solo
    miente la procedencia.
    """

    establecimiento: Dict[str, Any]
    consulta: str
    texto_web: str
    fuente: str
    tipo: str
    texto: str


def _campo(establecimiento: Any, clave: str, por_defecto: str = "") -> str:
    if not isinstance(establecimiento, dict):
        return por_defecto
    return str(establecimiento.get(clave) or por_defecto).strip()


# ----------------------------------------------------------------------
# Nodo 1 — de dónde sale el texto del sitio
# ----------------------------------------------------------------------

def _desde_cache(establecimiento: Dict[str, Any],
                 cache: Optional[Callable[[str], Optional[str]]]) -> str:
    """El texto ya extraído fuera de línea, si lo hay. Es la capa más barata."""
    if cache is None:
        return ""
    try:
        return str(cache(_campo(establecimiento, "id")) or "").strip()
    # La caché es un lujo, no el trabajo: no puede tumbar al agente.
    except Exception:
        return ""


def _desde_tavily(establecimiento: Dict[str, Any],
                  buscador: Optional[Callable[[Dict[str, str]], Any]]) -> str:
    """
    El respaldo para las páginas que arman su contenido con JavaScript.

    Es el caso de `WWW.ADTEC.COM.MX`, que devolvió 16 caracteres en la medición
    de §2.3: el HTML llega y el contenido no.
    """
    if buscador is None:
        return ""
    consulta = f"{_campo(establecimiento, 'nom_estab')} {_campo(establecimiento, 'www')}"
    try:
        documentos = buscador({"query": consulta.strip()}) or []
    except Exception:
        return ""
    return " ".join(str(d.get("content", "")) for d in documentos if isinstance(d, dict)).strip()


def nodo_sitio(estado: Dict[str, Any], extractor: Optional[Callable[[Any], Dict[str, Any]]] = None,
               cache: Optional[Callable[[str], Optional[str]]] = None,
               buscador: Optional[Callable[[Dict[str, str]], Any]] = None,
               guardar_cache: Optional[Callable[[str, str], None]] = None) -> Dict[str, Any]:
    """
    `check_website`, con los tres estados. Devuelve `texto_web` y `fuente`.

    El orden es el del costo, no el de la calidad: caché (gratis), lectura en
    vivo (menos de un segundo en la mayoría) y Tavily (una llamada de pago).
    """
    establecimiento = estado.get("establecimiento") or {}

    texto = _desde_cache(establecimiento, cache)
    if texto:
        return {"texto_web": texto, "fuente": FUENTE_CACHE}

    if extractor is not None and _campo(establecimiento, "www"):
        lectura = extractor(establecimiento.get("www")) or {}
        if lectura.get("success") and lectura.get("texto"):
            _guardar(guardar_cache, _campo(establecimiento, "id"), str(lectura["texto"]))
            return {"texto_web": str(lectura["texto"]), "fuente": FUENTE_WEB}

    texto = _desde_tavily(establecimiento, buscador)
    if texto:
        return {"texto_web": texto, "fuente": FUENTE_TAVILY}

    return {"texto_web": "", "fuente": FUENTE_SIN_WEB}


def _guardar(guardar_cache: Optional[Callable[[str, str], None]],
             denue_id: str, texto: str) -> None:
    """
    Deja el texto leído en la caché para no volver a pedirlo.

    Falla en silencio a propósito: que no se pueda escribir la caché no puede
    impedir que el vendedor reciba su análisis. Es un lujo, no el trabajo.
    """
    if guardar_cache is None or not denue_id:
        return
    try:
        guardar_cache(denue_id, texto)
    except Exception:
        pass


def ruta_despues_del_sitio(estado: Dict[str, Any]) -> str:
    """
    Con texto se analiza; sin texto se redacta el contacto.

    Es la bifurcación del notebook, y la de redacción es la que más corre: solo
    el 13.6% de los establecimientos tiene sitio.
    """
    return "analizar" if estado.get("texto_web") else "redactar"


# ----------------------------------------------------------------------
# Nodos 2 y 3 — lo que escribe el LLM
# ----------------------------------------------------------------------

def _texto_del_llm(llm: Any, prompt: str) -> str:
    """El contenido de la respuesta, venga como objeto de mensaje o como texto."""
    respuesta = llm.invoke(prompt)
    contenido = getattr(respuesta, "content", respuesta)
    return str(contenido).strip()


def nodo_analizar(estado: Dict[str, Any], llm: Any) -> Dict[str, Any]:
    """`analyze_node`: qué es este negocio, leído de su propio sitio."""
    establecimiento = estado.get("establecimiento") or {}
    prompt = PROMPT_ANALISIS.format(
        nombre=_campo(establecimiento, "nom_estab", "(sin nombre)"),
        giro=_campo(establecimiento, "nombre_act"),
        consulta=estado.get("consulta") or "Evalúa si sirve como proveedor.",
        texto=str(estado.get("texto_web", ""))[:TECHO_CONTEXTO_CHARS],
    )
    return {"tipo": TIPO_ANALISIS, "texto": _texto_del_llm(llm, prompt)}


def nodo_redactar(estado: Dict[str, Any], llm: Any) -> Dict[str, Any]:
    """
    `draft_node`: el correo de contacto, con o sin contexto del sitio.

    El contexto se pega solo si existe. Sin esa guarda, el prompt llevaría un
    bloque "TEXTO DE SU SITIO:" vacío y el modelo tiende a rellenarlo — que es
    la forma más limpia de inventar datos de un negocio real.
    """
    establecimiento = estado.get("establecimiento") or {}
    texto_web = str(estado.get("texto_web", ""))[:TECHO_CONTEXTO_CHARS]
    contexto = f"\nLO QUE DICE SU SITIO:\n{texto_web}" if texto_web else ""
    prompt = PROMPT_CORREO.format(
        nombre=_campo(establecimiento, "nom_estab", "(sin nombre)"),
        giro=_campo(establecimiento, "nombre_act"),
        alcaldia=_campo(establecimiento, "municipio"),
        consulta=estado.get("consulta") or "Cotización de materiales para obra.",
        contexto=contexto,
    )
    return {"tipo": TIPO_CORREO, "texto": _texto_del_llm(llm, prompt)}


# ----------------------------------------------------------------------
# Lo que se inyecta en producción
# ----------------------------------------------------------------------

def llm_disponible() -> Any:
    """
    El LLM del proyecto, o `None` si no está configurado.

    Devolver `None` en vez de lanzar es el criterio de `plano.llm_disponible()`:
    la falta de clave no puede tumbar el módulo entero, solo limitar lo que hace.
    """
    from api import paperclip_agents

    clave = os.environ.get("GROQ_API_KEY")
    if not clave or paperclip_agents.ChatGroq is None:
        return None
    try:
        return paperclip_agents.ChatGroq(model=MODELO, temperature=0.3, api_key=clave)
    except Exception as exc:
        print(f"[prospeccion] No se pudo construir el LLM: {exc}")
        return None


def extractor_disponible() -> Callable[[Any], Dict[str, Any]]:
    """La lectura en vivo. Siempre disponible: es biblioteca estándar."""
    from api.services import extractor_web

    return extractor_web.extraer_texto


def buscador_disponible() -> Optional[Callable[[Dict[str, str]], Any]]:
    """
    Tavily, o `None` sin clave. Ya es dependencia declarada y hay precedente de
    uso en `api/engineering_agent.py:107`.
    """
    clave = os.environ.get("TAVILY_API_KEY")
    if not clave:
        return None
    try:
        from langchain_community.tools.tavily_search import TavilySearchResults

        return TavilySearchResults(max_results=2, api_key=clave).invoke
    except Exception as exc:
        print(f"[prospeccion] Tavily no disponible: {exc}")
        return None


# ----------------------------------------------------------------------
# El grafo
# ----------------------------------------------------------------------

def construir_grafo(llm: Any, extractor=None, cache=None, buscador=None, guardar_cache=None):
    """
    El grafo de LangGraph, con los colaboradores ya atados a cada nodo.

    Se compila por llamada y no una vez por proceso: los colaboradores cambian
    entre peticiones —la caché depende del establecimiento— y un grafo compilado
    con la caché de otro negocio devolvería el texto equivocado.
    """
    from langgraph.graph import END, START, StateGraph

    grafo = StateGraph(EstadoProspeccion)
    grafo.add_node("sitio", lambda estado: nodo_sitio(
        estado, extractor=extractor, cache=cache, buscador=buscador,
        guardar_cache=guardar_cache))
    grafo.add_node("analizar", lambda estado: nodo_analizar(estado, llm))
    grafo.add_node("redactar", lambda estado: nodo_redactar(estado, llm))

    grafo.add_edge(START, "sitio")
    grafo.add_conditional_edges("sitio", ruta_despues_del_sitio,
                                {"analizar": "analizar", "redactar": "redactar"})
    grafo.add_edge("analizar", END)
    grafo.add_edge("redactar", END)
    return grafo.compile()


def ejecutar(establecimiento: Dict[str, Any], consulta: str = "", llm: Any = None,
             extractor=None, cache=None, buscador=None, guardar_cache=None) -> Dict[str, Any]:
    """
    Corre el agente sobre un establecimiento. Nunca lanza.

    Sin LLM no se inventa una respuesta: se dice que falta la clave. Un análisis
    fabricado sin modelo sería indistinguible de uno real para quien lo lee, que
    es el peor fallo posible en algo que acaba en un correo a un tercero.
    """
    if llm is None:
        return {"success": False, "message":
                "El agente de IA no está disponible en este despliegue "
                "(falta GROQ_API_KEY). El resto del módulo sigue funcionando."}

    inicial = {"establecimiento": establecimiento or {}, "consulta": consulta or ""}
    try:
        final = construir_grafo(llm, extractor, cache, buscador, guardar_cache).invoke(inicial)
    except Exception as exc:
        return {"success": False, "message":
                f"El agente no pudo completar el análisis ({exc}). Vuelve a intentarlo."}

    return {"success": True, "tipo": final.get("tipo", TIPO_CORREO),
            "texto": final.get("texto", ""), "fuente": final.get("fuente", FUENTE_SIN_WEB)}
