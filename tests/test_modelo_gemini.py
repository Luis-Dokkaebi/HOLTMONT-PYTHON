"""
El identificador del modelo de Gemini: uno solo, vigente, y en todos los sitios.

Por qué existe esta prueba
--------------------------
Es el mismo fallo que `tests/test_modelo_groq.py` documenta para Groq, un
proveedor más allá, y quedó a medio arreglar.

Google retira modelos. `gemini-1.5-flash` y `gemini-1.5-pro` responden 404 en
`v1beta` a las API keys emitidas después de su retiro. `api/services/tracker_store.py`
ya lo sufrió y lo arregló para el agente de métricas —cambió el valor fijo por
un catálogo con degradación—, pero el identificador seguía escrito a mano en
otros dos sitios que nadie revisó al hacer aquel arreglo:

* `api/paperclip_agents.py`, con `"gemini-1.5-pro"` fijo. Es el LLM de texto de
  toda la agencia (levantamiento, cálculo y precios): sin `GEMINI_API_KEY` cae a
  Groq y funciona, y **con** la key configurada se rompía. Configurar una
  credencial válida empeoraba el sistema, que es la peor forma de un fallo.
* `CODIGO.js`, con `"gemini-1.5-flash"` en `METRICS_CONFIG.geminiModel` y otra
  vez en `transcribirConGemini`. El comentario de `tracker_store.py` nombra ese
  archivo como pendiente; esto lo cierra.

La lección de Groq fue que un identificador copiado en N sitios se migra en
dos y se olvida en cinco. Aquí se comprueba lo mismo para Gemini.
"""

import os
import pathlib
import sys

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from api import modelos_llm, paperclip_agents  # noqa: E402
from api.services import tracker_store  # noqa: E402

RAIZ = pathlib.Path(__file__).resolve().parent.parent

# Los modelos que Google retiró. Nunca deben volver al código.
MODELOS_RETIRADOS = ("gemini-1.5-flash", "gemini-1.5-pro")

PAQUETES = ("api", "streamlit_cotizador")

# El backend de Apps Script. No es Python y no lo alcanza `_modulos_desplegados`,
# pero llama a la misma API de Google con el mismo identificador caducado.
CODIGO_GAS = RAIZ / "CODIGO.js"


def _modulos_desplegados() -> list[pathlib.Path]:
    return sorted(
        ruta
        for paquete in PAQUETES
        for ruta in (RAIZ / paquete).rglob("*.py")
    )


def _menciona_como_valor(ruta: pathlib.Path, modelo: str) -> bool:
    """
    Si el archivo escribe el identificador entre comillas, es decir, como el
    valor que viajaría a la API.

    Nombrarlo en prosa no cuenta: `api/services/tracker_store.py` cita el
    modelo retirado —entre acentos graves, en un comentario— para dejar
    constancia de por qué su catálogo es una lista. Contar esa mención
    obligaría a borrar la explicación del fallo del archivo que lo arregla.
    """
    texto = ruta.read_text(encoding="utf-8")
    return any(f"{comilla}{modelo}{comilla}" in texto for comilla in ('"', "'"))


def _aparece_en_gas(modelo: str) -> bool:
    """
    En `CODIGO.js` el identificador viaja por dos caminos, y los dos cuentan:
    como valor entre comillas de `METRICS_CONFIG`, o interpolado en la ruta de
    la URL de Google (`.../models/<modelo>:generateContent`). Nombrarlo en un
    comentario para explicar por qué se cambió no cuenta, igual que en Python.
    """
    texto = CODIGO_GAS.read_text(encoding="utf-8")
    entre_comillas = any(f"{c}{modelo}{c}" in texto for c in ('"', "'", "`"))
    return entre_comillas or f"models/{modelo}" in texto


# --------------------------------------------------------------------------- #
# 1. Los modelos retirados no vuelven
# --------------------------------------------------------------------------- #

@pytest.mark.parametrize("modelo", MODELOS_RETIRADOS)
def test_ningun_modulo_desplegado_menciona_un_modelo_retirado(modelo):
    culpables = [
        str(ruta.relative_to(RAIZ))
        for ruta in _modulos_desplegados()
        if _menciona_como_valor(ruta, modelo)
    ]
    assert culpables == [], (
        f"{modelo} responde 404 en v1beta a las API keys emitidas tras su "
        f"retiro. Archivos: {culpables}"
    )


@pytest.mark.parametrize("modelo", MODELOS_RETIRADOS)
def test_el_backend_de_apps_script_tampoco_lo_menciona(modelo):
    """
    `CODIGO.js` no se lintea con el resto y su fallo no lo ve ninguna prueba de
    Python: llega como "Error al consultar Gemini" en el dashboard.
    """
    assert not _aparece_en_gas(modelo), (
        f"CODIGO.js sigue pidiendo {modelo}, que Google retiró."
    )


# --------------------------------------------------------------------------- #
# 2. Un identificador, un sitio
# --------------------------------------------------------------------------- #

def test_el_identificador_vigente_esta_escrito_una_sola_vez():
    escrito_en = [
        str(ruta.relative_to(RAIZ))
        for ruta in _modulos_desplegados()
        if _menciona_como_valor(ruta, modelos_llm.MODELO_GEMINI)
    ]
    assert escrito_en == ["api/modelos_llm.py"], (
        "El identificador de Gemini debe escribirse solo en api/modelos_llm.py "
        f"e importarse desde ahí. Aparece en: {escrito_en}"
    )


def test_el_catalogo_del_agente_de_metricas_sale_del_sitio_unico():
    """
    `tracker_store` mantiene su cascada de degradación —es lo que le da un
    segundo intento cuando Google retira el primero—, pero los nombres salen
    del módulo que los centraliza, no de una lista copiada.
    """
    assert list(tracker_store.GEMINI_MODELS) == list(modelos_llm.MODELOS_GEMINI)


def test_el_modelo_por_defecto_es_la_cabeza_del_catalogo(monkeypatch):
    monkeypatch.delenv("GEMINI_MODEL", raising=False)
    import importlib

    recargado = importlib.reload(modelos_llm)
    try:
        assert recargado.MODELO_GEMINI == recargado.MODELOS_GEMINI[0]
        assert "1.5" not in recargado.MODELO_GEMINI
    finally:
        importlib.reload(modelos_llm)


def test_el_entorno_puede_fijar_otro_modelo(monkeypatch):
    """
    Google mueve su catálogo más rápido que un despliegue. `GEMINI_MODEL` deja
    apuntar a uno nuevo sin tocar código, igual que `GROQ_MODELO`.
    """
    monkeypatch.setenv("GEMINI_MODEL", "gemini-3-pro")
    import importlib

    recargado = importlib.reload(modelos_llm)
    try:
        assert recargado.MODELO_GEMINI == "gemini-3-pro"
    finally:
        monkeypatch.delenv("GEMINI_MODEL", raising=False)
        importlib.reload(modelos_llm)


# --------------------------------------------------------------------------- #
# 3. Lo que de verdad sale hacia Google
# --------------------------------------------------------------------------- #

class GeminiEspia:
    """Un `ChatGoogleGenerativeAI` de mentira, en la frontera de la librería."""

    ultimos_kwargs: dict = {}

    def __init__(self, **kwargs):
        GeminiEspia.ultimos_kwargs = kwargs


def test_la_agencia_paperclip_pide_el_modelo_vigente(monkeypatch):
    """
    Con `GEMINI_API_KEY` puesta, la agencia usa Gemini para el texto pesado. El
    argumento `model` se mide en la llamada real a la librería, no leyendo el
    archivo.
    """
    GeminiEspia.ultimos_kwargs = {}
    monkeypatch.setenv("GEMINI_API_KEY", "AIza-de-mentira")
    monkeypatch.setattr(paperclip_agents, "ChatGoogleGenerativeAI", GeminiEspia)
    monkeypatch.setattr(paperclip_agents, "ChatGroq", lambda **kwargs: object())
    monkeypatch.setattr(paperclip_agents, "build_paperclip_graph",
                        lambda llm_text, llm_structured: _GrafoInerte())

    paperclip_agents.run_paperclip_agency("una barda", api_key="groq-de-mentira")

    assert GeminiEspia.ultimos_kwargs["model"] == modelos_llm.MODELO_GEMINI


class _GrafoInerte:
    """No ejecuta la agencia: aquí se mide con qué modelo se construyó el LLM."""

    def invoke(self, _estado):
        return {}


# --------------------------------------------------------------------------- #
# 4. La clave no vive en el código
# --------------------------------------------------------------------------- #

def test_codigo_js_no_trae_una_api_key_de_google_escrita():
    """
    `transcribirConGemini` llevaba una key de Google Studio literal en el
    fuente (`AIzaSy...`). Una key en el repositorio es una key comprometida:
    cualquiera con acceso de lectura puede gastarla, y rotarla obliga a un
    despliegue. El resto del archivo ya la leía de las Propiedades del Script.
    """
    import re

    texto = CODIGO_GAS.read_text(encoding="utf-8")
    encontradas = re.findall(r"AIza[0-9A-Za-z_\-]{30,}", texto)
    assert encontradas == [], (
        "Hay una API key de Google escrita en CODIGO.js. Debe salir de "
        "PropertiesService.getScriptProperties()."
    )
