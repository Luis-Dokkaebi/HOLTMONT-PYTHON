"""
El backend del dictado de la Pre Work Order: `/api/transcribe_and_analyze`.

`tests/test_dictado_prework_ui.py` cubre el botón; aquí va lo que el navegador
no puede ver. Las dos cosas que se comprueban fallaban en silencio y le costaban
a la persona exactamente lo mismo: hablar cinco minutos y quedarse sin texto.

1. **La palabra "error" dentro del dictado.** El endpoint decidía si la
   transcripción había fallado con `if "Error" in transcription`. Es una
   subcadena, no un código: una frase de taller tan normal como "revisar el
   error del tablero" se tomaba por un fallo del proveedor y el texto se tiraba.
   En un formulario cuyo propósito es describir trabajos de reparación, esa
   palabra no es un caso raro: es vocabulario del oficio.

2. **La extracción estructurada no es el entregable del botón.** El endpoint
   hace dos cosas —transcribir con Whisper y luego pedirle al modelo que
   estructure el texto— y devolvía `success: false` si fallaba **cualquiera** de
   las dos. El micrófono solo usa `transcription`: perder el dictado porque el
   segundo modelo se cayó, o porque devolvió un JSON que no encaja en el
   esquema, es tirar un trabajo que ya estaba hecho y cobrado.

Ninguna de las dos llama a Groq: la suite no tiene clave y no la va a tener.
Se doblan `transcribir_audio` y `extraer_informacion` —la frontera con el
proveedor— y se ejerce el endpoint de verdad con `TestClient`.
"""

from __future__ import annotations

import io
import json
import os
import re
import shutil
import subprocess

import pytest
from fastapi.testclient import TestClient

from api import main as api_main

# Vocabulario real del formulario. No es un caso rebuscado: la Pre Work Order
# existe para cotizar reparaciones, y "error" aparece describiéndolas.
# Whisper puntúa y pone mayúscula al abrir frase, así que la palabra llega
# capitalizada en cuanto la persona empieza una oración con ella.
DICTADO_CON_LA_PALABRA_ERROR = (
    "Hay que revisar el tablero principal de la nave dos. "
    "Error del operador al medir, se repite el levantamiento. "
    "Cotizar el cambio de dos contactores"
)


def _cliente(monkeypatch, transcripcion, extraccion):
    """El endpoint real, con el proveedor de IA doblado en su frontera."""
    monkeypatch.setenv("GROQ_API_KEY", "clave-de-prueba")
    monkeypatch.setattr(api_main, "transcribir_audio",
                        lambda api_key, contenido, filename="audio.wav": transcripcion)
    monkeypatch.setattr(api_main, "extraer_informacion",
                        lambda api_key, texto: extraccion)
    return TestClient(api_main.app)


def _enviar(cliente):
    return cliente.post(
        "/api/transcribe_and_analyze",
        files={"file": ("audio.webm", io.BytesIO(b"audio-de-prueba"), "audio/webm")},
    )


def test_un_dictado_que_dice_la_palabra_error_no_se_toma_por_un_fallo(monkeypatch):
    """Es texto del oficio, no un código de error del proveedor."""
    cliente = _cliente(monkeypatch, DICTADO_CON_LA_PALABRA_ERROR,
                       {"extraction": {"cliente": "MB"}, "error": ""})

    cuerpo = _enviar(cliente).json()

    assert cuerpo["success"] is True, (
        f"El dictado se descartó por contener la palabra 'error': {cuerpo}")
    assert cuerpo["transcription"] == DICTADO_CON_LA_PALABRA_ERROR


def test_un_fallo_real_del_proveedor_si_se_reporta(monkeypatch):
    """La contraparte: si Whisper falla de verdad, no se finge un dictado."""
    cliente = _cliente(monkeypatch, "Error: Falta GROQ_API_KEY.",
                       {"extraction": {}, "error": ""})

    cuerpo = _enviar(cliente).json()

    assert cuerpo["success"] is False
    assert "GROQ_API_KEY" in cuerpo["message"]


def test_el_dictado_se_entrega_aunque_la_extraccion_se_caiga(monkeypatch):
    """El botón del micrófono solo pide texto; el resto es un extra."""
    cliente = _cliente(monkeypatch, DICTADO_CON_LA_PALABRA_ERROR,
                       {"extraction": None, "error": "El modelo devolvió un JSON inválido"})

    cuerpo = _enviar(cliente).json()

    assert cuerpo["success"] is True, (
        "Se perdió una transcripción buena porque el segundo modelo falló: "
        f"{cuerpo}")
    assert cuerpo["transcription"] == DICTADO_CON_LA_PALABRA_ERROR
    assert cuerpo["data"] is None
    assert "JSON inválido" in cuerpo["message"], (
        "El fallo de la extracción debe seguir viéndose, aunque no tire el dictado.")


def test_un_audio_mudo_se_dice_y_no_se_devuelve_un_dictado_vacio(monkeypatch):
    """Whisper devuelve "" con el micrófono apagado o una grabación de 0 bytes.

    Entregarlo como éxito hacía que el frontend pegara una cadena vacía en la
    descripción: desde la pantalla, "no se entendió nada" y "el botón no hizo
    nada" se ven exactamente igual.
    """
    cliente = _cliente(monkeypatch, "   ", {"extraction": {}, "error": ""})

    cuerpo = _enviar(cliente).json()

    assert cuerpo["success"] is False
    assert "micrófono" in cuerpo["message"]
    assert cuerpo["transcription"] == ""


def test_sin_clave_de_groq_se_dice_que_falta_y_no_se_intenta_transcribir(monkeypatch):
    """Un 400 con el motivo, no un 500 opaco ni un texto vacío."""
    monkeypatch.delenv("GROQ_API_KEY", raising=False)
    llamadas = []
    monkeypatch.setattr(api_main, "transcribir_audio",
                        lambda *a, **k: llamadas.append(a) or "")

    respuesta = _enviar(TestClient(api_main.app, raise_server_exceptions=False))

    assert respuesta.status_code == 400
    assert "GROQ_API_KEY" in respuesta.json()["detail"]
    assert llamadas == [], "Se llamó al proveedor sabiendo que no había clave."


@pytest.mark.parametrize(
    "texto",
    ["Error: La librería 'groq' no está instalada.",
     "Error: Falta GROQ_API_KEY.",
     "Error en transcripción: connection reset by peer"],
)
def test_los_tres_fallos_que_transcribir_audio_sabe_devolver_se_reconocen(texto):
    """El productor y el consumidor comparten la definición de 'esto falló'.

    `transcribir_audio` devuelve una cadena tanto si transcribió como si falló.
    Quien la llama tiene que poder distinguirlas sin adivinar, y sin que una
    frase del usuario que empiece parecido cuente como fallo.
    """
    from api.ai_utils import es_error_de_transcripcion

    assert es_error_de_transcripcion(texto) is True


@pytest.mark.parametrize(
    "texto",
    [DICTADO_CON_LA_PALABRA_ERROR,
     "Error del operador al medir, hay que repetir el levantamiento",
     "",
     "Se detectó un Error en transcripción de las cotas del plano",
     # Los dos siguientes llevan el prefijo COMPLETO, pero dentro de la frase y
     # no al principio: es lo que pasa cuando alguien dicta lo que leyó en una
     # pantalla. Distinguen `startswith` de `in`, que es justo la diferencia
     # entre el arreglo y el bug de origen; sin ellos, volver a poner `in` no
     # rompería ninguna prueba.
     "Anotar en la bitácora: Error: falta el plano que mandó el cliente",
     "El sistema del cliente marcaba Error en transcripción: se anexa la foto"],
)
def test_un_dictado_no_se_confunde_con_un_fallo(texto):
    from api.ai_utils import es_error_de_transcripcion

    assert es_error_de_transcripcion(texto) is False


# --------------------------------------------------------------------------- #
# El nombre con el que el audio llega al proveedor
# --------------------------------------------------------------------------- #
#
# Whisper decide el contenedor por la EXTENSIÓN del archivo, no por el
# `Content-Type`. El adaptador construía el nombre con el subtipo MIME pelado
# (`audio/x-m4a` → `audio.x-m4a`), que no es ninguna extensión: el proveedor
# devolvía un 400 por el envoltorio y el mensaje no mencionaba el formato, así
# que desde la pantalla solo se veía "no se pudo transcribir".
#
# Se evalúa la función real con Node en vez de leer el archivo: una prueba que
# buscara texto pasaría con cualquier otra forma de derivar la extensión.

ADAPTADOR = os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "api_service.js")

# (tipo MIME que entrega el navegador, extensión que Whisper espera)
FORMATOS = [
    ("audio/webm;codecs=opus", "webm"),   # Chrome y Firefox, escritorio y Android
    ("audio/mp4", "mp4"),                 # Safari: el iPad de obra
    ("audio/x-m4a", "m4a"),               # selector de archivos en iOS
    ("audio/x-wav", "wav"),
    ("audio/wave", "wav"),
    ("audio/ogg; codecs=opus", "ogg"),    # Firefox
    ("audio/aac", "m4a"),
    ("audio/mpeg", "mpeg"),
    ("", "webm"),                         # el navegador no dijo nada
]


def _extension_de_audio_en_node(mime: str) -> str:
    """Ejecuta `GoogleScriptRunAdapter.extensionDeAudio` tal cual está escrita."""
    with open(ADAPTADOR, encoding="utf-8") as fh:
        fuente = fh.read()

    m = re.search(r"^    static extensionDeAudio\(mimeType\) \{.*?^    \}", fuente,
                  re.S | re.M)
    assert m, "no se encontró `extensionDeAudio` en api_service.js"
    cuerpo = m.group(0).replace("    static extensionDeAudio", "function extensionDeAudio", 1)

    salida = subprocess.run(
        ["node", "-e", f"{cuerpo}\nconsole.log(extensionDeAudio({json.dumps(mime)}));"],
        capture_output=True, text=True, timeout=30, check=False)
    assert salida.returncode == 0, f"node falló: {salida.stderr}"
    return salida.stdout.strip()


@pytest.mark.skipif(shutil.which("node") is None, reason="node no está instalado")
@pytest.mark.parametrize(("mime", "extension"), FORMATOS)
def test_el_audio_se_sube_con_la_extension_que_whisper_entiende(mime, extension):
    assert _extension_de_audio_en_node(mime) == extension


@pytest.mark.skipif(shutil.which("node") is None, reason="node no está instalado")
def test_un_formato_desconocido_pasa_tal_cual_y_no_se_disfraza():
    """Inventarle una extensión plausible haría que el error llegara mintiendo."""
    assert _extension_de_audio_en_node("audio/3gpp") == "3gpp"


# --------------------------------------------------------------------------- #
# Las otras dos entradas de audio del repositorio
# --------------------------------------------------------------------------- #
#
# El mismo `if "Error" in texto` estaba copiado en los otros dos sitios que
# transcriben: el agente de preguntas de ingeniería (`process_audio`) y el
# dictado de la Pre Work Order de Streamlit. Los tres comparten ahora
# `es_error_de_transcripcion`, y aquí se comprueba que cada uno lo usa de
# verdad — no basta con que la función exista.


def test_el_agente_de_preguntas_no_confunde_un_dictado_con_un_fallo(monkeypatch):
    from api import engineering_agent

    monkeypatch.setenv("GROQ_API_KEY", "clave-de-prueba")
    monkeypatch.setattr(engineering_agent, "transcribir_con_groq",
                        lambda *a, **k: DICTADO_CON_LA_PALABRA_ERROR)
    monkeypatch.setattr(engineering_agent, "build_graph",
                        lambda llm, tavily: _GrafoFalso())
    monkeypatch.setattr(engineering_agent, "ChatGroq", lambda **k: object())

    resultado = engineering_agent.process_audio(b"audio-de-prueba")

    assert resultado["success"] is True, (
        f"El dictado se descartó por contener la palabra 'error': {resultado}")
    assert resultado["transcription"] == DICTADO_CON_LA_PALABRA_ERROR


def test_el_agente_de_preguntas_si_reporta_un_fallo_real(monkeypatch):
    from api import engineering_agent

    monkeypatch.setenv("GROQ_API_KEY", "clave-de-prueba")
    monkeypatch.setattr(engineering_agent, "transcribir_con_groq",
                        lambda *a, **k: "Error en transcripción: se cayó la red")

    resultado = engineering_agent.process_audio(b"audio-de-prueba")

    assert resultado["success"] is False
    assert "se cayó la red" in resultado["message"]


class _GrafoFalso:
    """El grafo de LangGraph, doblado: aquí se prueba el filtro, no el agente."""

    def invoke(self, estado, config=None):
        return {"draft_questions": "1. ¿Qué voltaje tiene el tablero?"}


def test_el_dictado_de_streamlit_sobrevive_a_un_fallo_de_la_extraccion(monkeypatch):
    """Misma regla que en la API: el texto ya está hecho, no se tira."""
    from streamlit_cotizador import work_order_view

    monkeypatch.setattr(work_order_view, "transcribir_audio",
                        lambda *a, **k: DICTADO_CON_LA_PALABRA_ERROR)
    monkeypatch.setattr(work_order_view, "extraer_informacion",
                        lambda *a, **k: {"extraction": None, "error": "modelo saturado"})

    resultado = work_order_view.procesar_audio_de_dictado("clave", b"audio-de-prueba")

    assert resultado["texto"] == DICTADO_CON_LA_PALABRA_ERROR
    assert resultado["datos"] is None
    assert resultado["error"] == "modelo saturado"


def test_el_dictado_de_streamlit_entrega_el_formulario_cuando_todo_va_bien(monkeypatch):
    from streamlit_cotizador import work_order_view

    monkeypatch.setattr(work_order_view, "transcribir_audio",
                        lambda *a, **k: DICTADO_CON_LA_PALABRA_ERROR)
    monkeypatch.setattr(work_order_view, "extraer_informacion",
                        lambda *a, **k: {"extraction": {"cliente": "MB"}, "error": ""})

    resultado = work_order_view.procesar_audio_de_dictado("clave", b"audio-de-prueba")

    assert resultado["error"] == ""
    assert resultado["datos"] == {"cliente": "MB"}


@pytest.mark.parametrize(
    ("transcripcion", "esperado"),
    [("Error: Falta GROQ_API_KEY.", "Error: Falta GROQ_API_KEY."),
     ("   ", "No se entendió nada en el audio. Revisa el micrófono y vuelve a grabar.")],
)
def test_el_dictado_de_streamlit_dice_por_que_no_hay_texto(monkeypatch, transcripcion, esperado):
    """Ni un fallo del proveedor ni un audio mudo se quedan sin explicación."""
    from streamlit_cotizador import work_order_view

    llamadas = []
    monkeypatch.setattr(work_order_view, "transcribir_audio", lambda *a, **k: transcripcion)
    monkeypatch.setattr(work_order_view, "extraer_informacion",
                        lambda *a, **k: llamadas.append(a) or {"extraction": {}, "error": ""})

    resultado = work_order_view.procesar_audio_de_dictado("clave", b"audio-de-prueba")

    assert resultado["error"] == esperado
    assert resultado["texto"] == ""
    assert llamadas == [], "Se pagó una llamada al segundo modelo sin texto que estructurar."


def test_un_reventon_inesperado_del_endpoint_se_devuelve_como_mensaje(monkeypatch):
    """Un 500 sin cuerpo JSON rompe `res.json()` y el aviso nunca llega a la pantalla."""
    monkeypatch.setenv("GROQ_API_KEY", "clave-de-prueba")

    def explota(*a, **k):
        raise RuntimeError("el proveedor cerró la conexión")

    monkeypatch.setattr(api_main, "transcribir_audio", explota)

    respuesta = _enviar(TestClient(api_main.app, raise_server_exceptions=False))

    assert respuesta.status_code == 200
    cuerpo = respuesta.json()
    assert cuerpo["success"] is False
    assert "cerró la conexión" in cuerpo["message"]
