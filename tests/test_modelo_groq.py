"""
El identificador del modelo de Groq: uno solo, vigente, y en todos los agentes.

Por qué existe esta prueba
--------------------------
Los agentes dejaron de funcionar con este 404 de Groq:

    The model llama-3.3-70b-versatile does not exist or you do not have
    access to it.

No fue un bug de lógica: fue un **nombre que caducó**. Groq retiró
`llama-3.3-70b-versatile` de su catálogo y el identificador estaba copiado a
mano en cinco archivos (`api/ai_utils.py`, `api/engineering_agent.py`,
`api/paperclip_agents.py`, `api/services/plano.py` y
`streamlit_cotizador/utils.py`), mientras otros dos módulos
(`agente_sql.py`, `prospeccion_agente.py`) ya habían migrado a
`openai/gpt-oss-120b`. Es decir: la migración anterior se hizo a mano, se
olvidaron cinco sitios, y nadie se enteró hasta que un usuario recibió el 404.

Un fallo así no lo atrapa ninguna prueba de negocio: el código es correcto, la
cadena se arma bien, y el error solo aparece contra la API real. Lo único que
lo puede atrapar antes es una prueba que mire el **identificador** en sí.

De ahí las tres cosas que se comprueban aquí:

1. Que el literal retirado no queda vivo en ningún módulo (regresión directa).
2. Que el identificador vive en **un solo sitio** (`api/modelos_llm.py`), para
   que la próxima retirada de catálogo se arregle en un renglón y no en siete.
3. Que cada punto de llamada le pide a Groq ese identificador y no otro, con
   una llamada real a la función, no leyendo el archivo.
"""

import importlib
import os
import pathlib
import sys

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from langchain_core.runnables import RunnableLambda

from api import ai_utils, engineering_agent, modelos_llm, paperclip_agents
from api.services import agente_sql, plano, prospeccion_agente

RAIZ = pathlib.Path(__file__).resolve().parent.parent

# El modelo que Groq retiró del catálogo. Nunca debe volver al código.
MODELO_RETIRADO = "llama-3.3-70b-versatile"

# Los paquetes que se despliegan. `HOLTMONT-PYTHON-main/` es una copia histórica
# que no se importa ni se lintea; queda fuera a propósito.
PAQUETES = ("api", "streamlit_cotizador")


def _modulos_desplegados() -> list[pathlib.Path]:
    return sorted(
        ruta
        for paquete in PAQUETES
        for ruta in (RAIZ / paquete).rglob("*.py")
    )


def _menciona_como_valor(ruta: pathlib.Path, modelo: str) -> bool:
    """
    Si el archivo escribe el identificador **entre comillas**, es decir, como el
    valor que viajaría a la API.

    La distinción no es un tecnicismo: `api/modelos_llm.py` nombra el modelo
    retirado en su docstring para dejar constancia de por qué existe el módulo.
    Contar esa mención como una infracción obligaría a borrar la explicación del
    fallo justo del archivo que lo arregla.
    """
    texto = ruta.read_text(encoding="utf-8")
    return f'"{modelo}"' in texto or f"'{modelo}'" in texto


class ChatGroqEspia:
    """
    Un `ChatGroq` de mentira que solo recuerda con qué modelo lo construyeron.

    Va en la frontera —la librería del proveedor— y no sobre la función que se
    está probando: lo que se mide es el argumento real que saldría hacia Groq.
    """

    ultimos_kwargs: dict = {}

    def __init__(self, **kwargs):
        ChatGroqEspia.ultimos_kwargs = kwargs
        self.modelo = kwargs.get("model")

    def with_structured_output(self, esquema):
        return RunnableLambda(lambda _: esquema())

    def invoke(self, *_args, **_kwargs):
        resp = type("_Resp", (), {})()
        resp.content = "texto"
        return resp

    def __call__(self, *args, **kwargs):
        return self.invoke(*args, **kwargs)


@pytest.fixture
def espia(monkeypatch):
    ChatGroqEspia.ultimos_kwargs = {}
    return ChatGroqEspia


# --------------------------------------------------------------------------- #
# 1. El modelo retirado no vuelve
# --------------------------------------------------------------------------- #

def test_ningun_modulo_desplegado_menciona_el_modelo_retirado():
    """
    La regresión, en su forma más directa: si alguien vuelve a escribir
    `llama-3.3-70b-versatile` en el código que se despliega, esto se pone rojo
    aquí y no en producción con un 404 delante de un usuario.
    """
    culpables = [
        str(ruta.relative_to(RAIZ))
        for ruta in _modulos_desplegados()
        if _menciona_como_valor(ruta, MODELO_RETIRADO)
    ]
    assert culpables == [], (
        f"{MODELO_RETIRADO} ya no existe en el catálogo de Groq: "
        f"cada llamada devuelve 404 model_not_found. Archivos: {culpables}"
    )


# --------------------------------------------------------------------------- #
# 2. Un identificador, un sitio
# --------------------------------------------------------------------------- #

def test_el_identificador_del_modelo_esta_escrito_una_sola_vez():
    """
    Lo que hizo caro el fallo no fue el nombre viejo: fue que estaba copiado
    siete veces y la migración anterior solo arregló dos. Mientras el literal
    viva en un único archivo, la próxima retirada de catálogo cuesta un renglón.
    """
    escrito_en = [
        str(ruta.relative_to(RAIZ))
        for ruta in _modulos_desplegados()
        if _menciona_como_valor(ruta, modelos_llm.MODELO_GROQ)
    ]
    assert escrito_en == ["api/modelos_llm.py"], (
        "El identificador del modelo debe escribirse solo en api/modelos_llm.py "
        f"e importarse desde ahí. Aparece en: {escrito_en}"
    )


def test_el_modelo_por_defecto_es_el_del_catalogo_vigente(monkeypatch):
    """
    Sin `GROQ_MODELO` en el entorno, el proyecto habla con el modelo que Groq sí
    tiene publicado. La prueba fija el valor a propósito: es el dato que hay que
    revisar cuando el proveedor mueva su catálogo otra vez.
    """
    monkeypatch.delenv("GROQ_MODELO", raising=False)
    recargado = importlib.reload(modelos_llm)
    try:
        assert recargado.MODELO_GROQ == "openai/gpt-oss-120b"
    finally:
        importlib.reload(modelos_llm)


def test_el_entorno_puede_fijar_otro_modelo_sin_tocar_codigo(monkeypatch):
    """
    Cuando el proveedor retira un modelo, el arreglo no puede depender de un
    despliegue. `GROQ_MODELO` deja cambiarlo desde el entorno.
    """
    monkeypatch.setenv("GROQ_MODELO", "openai/gpt-oss-20b")
    recargado = importlib.reload(modelos_llm)
    try:
        assert recargado.MODELO_GROQ == "openai/gpt-oss-20b"
    finally:
        monkeypatch.delenv("GROQ_MODELO", raising=False)
        importlib.reload(modelos_llm)


def test_un_valor_en_blanco_no_deja_al_proyecto_sin_modelo(monkeypatch):
    """
    `GROQ_MODELO=""` (o con espacios) es lo que deja un `.env` a medio llenar.
    Tomarlo al pie de la letra mandaría `model=""` a Groq y devolvería otro 404,
    esta vez sin nombre que buscar en el catálogo.
    """
    monkeypatch.setenv("GROQ_MODELO", "   ")
    recargado = importlib.reload(modelos_llm)
    try:
        assert recargado.MODELO_GROQ == "openai/gpt-oss-120b"
    finally:
        monkeypatch.delenv("GROQ_MODELO", raising=False)
        importlib.reload(modelos_llm)


# --------------------------------------------------------------------------- #
# 3. Cada punto de llamada pide ese modelo, comprobado llamando
# --------------------------------------------------------------------------- #

def test_la_extraccion_del_prework_order_pide_el_modelo_compartido(monkeypatch, espia):
    """`api/ai_utils.py`: la nota de voz de la Pre Work Order."""
    monkeypatch.setattr(ai_utils, "ChatGroq", espia)

    salida = ai_utils.extraer_informacion("clave-de-prueba", "texto de la visita")

    assert salida["error"] == ""
    assert espia.ultimos_kwargs["model"] == modelos_llm.MODELO_GROQ


def test_la_extraccion_del_cotizador_pide_el_modelo_compartido(monkeypatch, espia):
    """`streamlit_cotizador/utils.py`: la misma extracción desde Streamlit."""
    from streamlit_cotizador import utils

    monkeypatch.setattr(utils, "ChatGroq", espia)

    salida = utils.extraer_informacion("clave-de-prueba", "texto de la visita")

    assert salida["error"] == ""
    assert espia.ultimos_kwargs["model"] == modelos_llm.MODELO_GROQ


def test_el_agente_de_ingenieria_pide_el_modelo_compartido(monkeypatch, espia):
    """`api/engineering_agent.py`: el grafo que arma la propuesta técnica."""
    monkeypatch.setenv("GROQ_API_KEY", "clave-de-prueba")
    monkeypatch.delenv("TAVILY_API_KEY", raising=False)
    monkeypatch.setattr(engineering_agent, "ChatGroq", espia)
    monkeypatch.setattr(engineering_agent, "transcribir_con_groq",
                        lambda *_a, **_k: "necesito una nave industrial")
    monkeypatch.setattr(engineering_agent, "build_graph",
                        lambda _llm, _tool: RunnableLambda(lambda estado: estado))

    engineering_agent.process_audio(b"audio", "nota.wav")

    assert espia.ultimos_kwargs["model"] == modelos_llm.MODELO_GROQ


def test_la_agencia_paperclip_pide_el_modelo_compartido(monkeypatch, espia):
    """`api/paperclip_agents.py`: el LLM que hace las salidas estructuradas."""
    monkeypatch.setenv("GROQ_API_KEY", "clave-de-prueba")
    monkeypatch.delenv("GEMINI_API_KEY", raising=False)
    monkeypatch.setattr(paperclip_agents, "ChatGroq", espia)
    monkeypatch.setattr(paperclip_agents, "build_paperclip_graph",
                        lambda _texto, _estructurado: RunnableLambda(lambda estado: estado))

    salida = paperclip_agents.run_paperclip_agency("una bodega de 8x5")

    assert salida["success"] is True
    assert espia.ultimos_kwargs["model"] == modelos_llm.MODELO_GROQ


def test_el_plano_2d_pide_el_modelo_compartido(monkeypatch, espia):
    """`api/services/plano.py`: el LLM que interpreta descripciones en prosa."""
    monkeypatch.setenv("GROQ_API_KEY", "clave-de-prueba")
    monkeypatch.setattr(paperclip_agents, "ChatGroq", espia)

    assert plano.llm_disponible() is not None
    assert espia.ultimos_kwargs["model"] == modelos_llm.MODELO_GROQ


def test_el_agente_sql_y_el_de_prospeccion_usan_el_mismo_modelo():
    """
    Estos dos ya estaban en `openai/gpt-oss-120b` cuando los otros cinco seguían
    en el modelo retirado: son la prueba de que dos identificadores separados
    acaban divergiendo. Ahora salen del mismo sitio.
    """
    assert agente_sql.MODELO == modelos_llm.MODELO_GROQ
    assert prospeccion_agente.MODELO == modelos_llm.MODELO_GROQ
