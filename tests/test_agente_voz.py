"""
La voz del Agente de Consultas (`api/services/voz.py`).

El módulo convierte en audio la respuesta que el agente ya redactó. Lo que se
prueba aquí **no** es cómo suena —eso no se puede probar— sino las cuatro cosas
de las que depende que sea seguro y honesto:

1. **Que no se lea texto crudo de la base.** `comentarios`, `comentarios_semana`
   y `concepto` son campos libres que captura cualquier usuario del Tracker
   (`api/services/agente_sql_esquemas.py` los marca como ruidosos). Si esas
   celdas llegaran íntegras al sintetizador, cualquiera podría hacer que una
   bocina en un congreso diga lo que quiera. El tope de caracteres y el filtro
   de caracteres de control son la mitigación que vive en este módulo; la
   garantía es que el frontend manda `agente.respuesta`, que es prosa del
   modelo, no celdas.
2. **Que sin clave no se finja audio.** Igual que `agente_sql.ejecutar` con el
   LLM: sin proveedor se dice qué falta, no se devuelve un WAV vacío que el
   navegador reproduce en silencio y nadie sabe por qué.
3. **Que el PCM de Google salga reproducible.** Gemini devuelve PCM crudo
   (`audio/L16;codec=pcm;rate=24000`), que ningún `<audio>` reproduce sin
   cabecera. Sin envolverlo en WAV el botón "no hace nada", sin error.
4. **Que la clave de Google se encuentre con el nombre que tiene puesto.** En el
   despliegue real está como `Gemini_Key`, no `GEMINI_API_KEY`, y ese fallo ya
   costó un incidente (commit 50c7330). Aquí se reutilizan los alias de
   `api/paperclip_agents.py` en vez de escribir un nombre nuevo.

El proveedor va doblado: es la frontera (red), igual que el LLM y la ejecución
de SQL en `tests/test_agente_sql.py`. Ninguna prueba sale a internet.
"""

from __future__ import annotations

import base64
import json
import struct
from typing import List, Tuple

import pytest

from api.services import voz

# Un PCM de juguete: 8 muestras de 16 bits. El contenido da igual; lo que se
# comprueba es la cabecera que se le pone delante.
PCM = b"\x01\x02" * 8
MIME_PCM = "audio/L16;codec=pcm;rate=24000"


class SintetizadorFalso:
    """Doble del proveedor. Guarda lo que se le pidió leer."""

    def __init__(self, mime: str = "audio/wav", audio: bytes = b"RIFFxxxxWAVE"):
        self.mime = mime
        self.audio = audio
        self.textos: List[str] = []

    def __call__(self, texto: str) -> Tuple[str, bytes]:
        self.textos.append(texto)
        return self.mime, self.audio


def _sin_claves(monkeypatch) -> None:
    """Deja el entorno sin ninguna clave de ningún proveedor."""
    from api.paperclip_agents import ALIAS_CLAVE_GEMINI, ALIAS_CLAVE_GROQ

    for nombre in (*ALIAS_CLAVE_GEMINI, *ALIAS_CLAVE_GROQ):
        monkeypatch.delenv(nombre, raising=False)
    monkeypatch.delenv(voz.ENV_PROVEEDOR, raising=False)


# ----------------------------------------------------------------------
# El recorte: lo que se deja leer y lo que no
# ----------------------------------------------------------------------


def test_un_texto_mas_largo_que_el_tope_se_recorta():
    recortado = voz.recortar("ñ" * (voz.TOPE_CARACTERES + 500))
    assert len(recortado) <= voz.TOPE_CARACTERES


def test_el_recorte_no_parte_una_palabra_por_la_mitad():
    """
    Un corte a mitad de palabra se oye como un balbuceo y hace dudar de todo lo
    anterior. Se corta en el último espacio que cabe.
    """
    texto = " ".join(["palabra"] * 400)
    recortado = voz.recortar(texto, tope=50)
    assert len(recortado) <= 50
    assert recortado.endswith("palabra")


def test_una_sola_palabra_mas_larga_que_el_tope_se_corta_igual():
    """Sin espacio donde cortar no hay excusa para pasarse del tope."""
    assert len(voz.recortar("a" * 100, tope=30)) == 30


def test_los_caracteres_de_control_no_llegan_al_sintetizador():
    """
    Nulos y campanas vienen de celdas capturadas a mano y rompen a los
    proveedores. El salto de línea sí se conserva: marca pausa al leer.
    """
    limpio = voz.recortar("hola\x00 mundo\x07\nadiós")
    assert "\x00" not in limpio
    assert "\x07" not in limpio
    assert "\n" in limpio
    assert "hola" in limpio and "adiós" in limpio


def test_un_texto_de_solo_espacios_cuenta_como_vacio():
    assert voz.recortar("   \t  \n ") == ""


# ----------------------------------------------------------------------
# El WAV: que el navegador pueda reproducirlo
# ----------------------------------------------------------------------


def test_el_wav_declara_riff_wave_y_el_tamano_real_de_los_datos():
    envuelto = voz.envolver_wav(PCM, 24000)
    assert envuelto[:4] == b"RIFF"
    assert envuelto[8:12] == b"WAVE"
    assert envuelto[12:16] == b"fmt "
    assert envuelto[36:40] == b"data"
    # El tamaño de la sección `data` es el del PCM, y el de RIFF, 36 más.
    assert struct.unpack("<I", envuelto[40:44])[0] == len(PCM)
    assert struct.unpack("<I", envuelto[4:8])[0] == len(PCM) + 36
    assert envuelto[44:] == PCM


def test_el_wav_declara_la_frecuencia_que_se_le_pasa():
    frecuencia = struct.unpack("<I", voz.envolver_wav(PCM, 16000)[24:28])[0]
    assert frecuencia == 16000


def test_la_frecuencia_sale_del_mime_que_manda_el_proveedor():
    assert voz.frecuencia_de("audio/L16;codec=pcm;rate=24000") == 24000
    assert voz.frecuencia_de("audio/L16; codec=pcm; rate=48000") == 48000


def test_un_mime_sin_frecuencia_cae_en_la_de_por_defecto():
    """
    Adivinar mal la frecuencia no falla: suena a cámara lenta o a ardilla. Por
    eso el valor por defecto es el que documenta Google, no un número redondo.
    """
    assert voz.frecuencia_de("audio/L16;codec=pcm") == voz.FRECUENCIA_POR_DEFECTO
    assert voz.frecuencia_de("") == voz.FRECUENCIA_POR_DEFECTO


def test_un_wav_del_proveedor_no_se_vuelve_a_envolver():
    """Groq ya devuelve WAV. Otra cabecera encima lo dejaría irreproducible."""
    ya_wav = b"RIFF????WAVEfmt "
    assert voz.a_wav("audio/wav", ya_wav) == ya_wav


def test_el_pcm_crudo_se_envuelve_antes_de_salir():
    envuelto = voz.a_wav(MIME_PCM, PCM)
    assert envuelto[:4] == b"RIFF"
    assert envuelto.endswith(PCM)


# ----------------------------------------------------------------------
# `sintetizar`: el orquestador. Nunca lanza.
# ----------------------------------------------------------------------


def test_un_texto_vacio_no_gasta_una_llamada_al_proveedor():
    doble = SintetizadorFalso()
    resultado = voz.sintetizar("   ", doble)
    assert resultado["success"] is False
    assert doble.textos == []
    assert "audio" not in resultado


def test_sin_proveedor_se_dice_que_falta_la_clave_y_no_se_finge_audio():
    resultado = voz.sintetizar("hay 12 cotizaciones pendientes", None)
    assert resultado["success"] is False
    assert "audio" not in resultado
    assert "GEMINI_API_KEY" in resultado["message"]
    assert "GROQ_API_KEY" in resultado["message"]


def test_al_proveedor_le_llega_el_texto_ya_recortado():
    """El tope se aplica antes de la red, no después: se paga por carácter."""
    doble = SintetizadorFalso()
    voz.sintetizar("palabra " * 5000, doble)
    assert len(doble.textos[0]) <= voz.TOPE_CARACTERES


def test_el_audio_vuelve_en_base64_y_declarado_como_wav():
    doble = SintetizadorFalso(mime=MIME_PCM, audio=PCM)
    resultado = voz.sintetizar("hay 12 cotizaciones pendientes", doble)
    assert resultado["success"] is True
    assert resultado["mime"] == "audio/wav"
    assert base64.b64decode(resultado["audio"])[:4] == b"RIFF"


def test_el_texto_leido_vuelve_para_que_se_vea_lo_que_se_escucho():
    """
    Si se recortó, quien escucha tiene derecho a saber que escuchó un trozo. Un
    resumen a medias que se presenta como completo es el fallo caro aquí.
    """
    resultado = voz.sintetizar("palabra " * 5000, SintetizadorFalso())
    assert resultado["recortado"] is True
    assert resultado["texto"] == voz.recortar("palabra " * 5000)


def test_un_texto_corto_no_se_marca_como_recortado():
    resultado = voz.sintetizar("doce cotizaciones", SintetizadorFalso())
    assert resultado["recortado"] is False


def test_un_fallo_del_proveedor_no_lanza_y_dice_el_motivo():
    def explota(_texto):
        raise RuntimeError("429 rate limit")

    resultado = voz.sintetizar("hay 12 cotizaciones", explota)
    assert resultado["success"] is False
    assert "429 rate limit" in resultado["message"]
    assert "audio" not in resultado


def test_un_proveedor_que_devuelve_audio_vacio_se_reporta_como_fallo():
    """Un WAV de cero bytes se reproduce en silencio: indistinguible de un bug."""
    resultado = voz.sintetizar("hay 12 cotizaciones", SintetizadorFalso(audio=b""))
    assert resultado["success"] is False
    assert "audio" not in resultado


# ----------------------------------------------------------------------
# Qué proveedor se elige
# ----------------------------------------------------------------------


def test_sin_ninguna_clave_no_hay_sintetizador(monkeypatch):
    _sin_claves(monkeypatch)
    assert voz.sintetizador_disponible() is None


def test_con_las_dos_claves_se_prefiere_google(monkeypatch):
    """
    Las voces de `playai-tts` están entrenadas en inglés y leen el español con
    acento; las de Gemini son multilingües. La respuesta del agente es en
    español (`agente_sql.PROMPT_RESPUESTA`), así que Google va primero.
    """
    _sin_claves(monkeypatch)
    monkeypatch.setenv("GEMINI_API_KEY", "clave-google")
    monkeypatch.setenv("GROQ_API_KEY", "clave-groq")
    assert voz.sintetizador_disponible().proveedor == "gemini"


def test_con_solo_la_clave_de_groq_se_usa_groq(monkeypatch):
    _sin_claves(monkeypatch)
    monkeypatch.setenv("GROQ_API_KEY", "clave-groq")
    assert voz.sintetizador_disponible().proveedor == "groq"


def test_la_clave_de_google_se_reconoce_con_el_nombre_del_despliegue(monkeypatch):
    """
    En Vercel está puesta como `Gemini_Key`. Las variables de entorno distinguen
    mayúsculas: leer solo `GEMINI_API_KEY` la deja invisible aunque esté ahí.
    """
    _sin_claves(monkeypatch)
    monkeypatch.setenv("Gemini_Key", "clave-google")
    assert voz.sintetizador_disponible().proveedor == "gemini"


def test_el_proveedor_se_puede_forzar_por_entorno(monkeypatch):
    """
    Para cuando la voz de Google no convenza y haya que cambiar sin desplegar,
    que es la misma razón por la que los modelos salen del entorno.
    """
    _sin_claves(monkeypatch)
    monkeypatch.setenv("GEMINI_API_KEY", "clave-google")
    monkeypatch.setenv("GROQ_API_KEY", "clave-groq")
    monkeypatch.setenv(voz.ENV_PROVEEDOR, "groq")
    assert voz.sintetizador_disponible().proveedor == "groq"


def test_forzar_un_proveedor_sin_su_clave_no_cae_en_el_otro(monkeypatch):
    """
    Silenciosamente usar el otro proveedor es peor que no sonar: se pidió una
    voz concreta y saldría otra sin decirlo.
    """
    _sin_claves(monkeypatch)
    monkeypatch.setenv("GROQ_API_KEY", "clave-groq")
    monkeypatch.setenv(voz.ENV_PROVEEDOR, "gemini")
    assert voz.sintetizador_disponible() is None


def test_los_modelos_y_las_voces_salen_del_entorno(monkeypatch):
    """
    Misma lección que `api/modelos_llm.py`: un identificador de modelo caduca, y
    cuando el proveedor lo retira responde 404 con la clave perfectamente bien.
    """
    _sin_claves(monkeypatch)
    monkeypatch.setenv("GEMINI_API_KEY", "clave-google")
    monkeypatch.setenv(voz.ENV_MODELO_GEMINI, "gemini-nuevo-tts")
    monkeypatch.setenv(voz.ENV_VOZ_GEMINI, "Aoede")
    elegido = voz.sintetizador_disponible()
    assert elegido.modelo == "gemini-nuevo-tts"
    assert elegido.voz == "Aoede"


# ----------------------------------------------------------------------
# La ruta HTTP
# ----------------------------------------------------------------------


def test_la_ruta_devuelve_el_audio_que_produjo_el_proveedor(monkeypatch):
    from fastapi.testclient import TestClient

    from api.main import app

    monkeypatch.setattr(voz, "sintetizador_disponible",
                        lambda: SintetizadorFalso(mime=MIME_PCM, audio=PCM))
    cuerpo = TestClient(app).post(
        "/api/agente/voz", json={"texto": "hay 12 cotizaciones pendientes"}).json()

    assert cuerpo["success"] is True
    assert cuerpo["mime"] == "audio/wav"
    assert base64.b64decode(cuerpo["audio"])[:4] == b"RIFF"


def test_la_ruta_sin_clave_explica_que_falta_en_vez_de_devolver_500(monkeypatch):
    from fastapi.testclient import TestClient

    from api.main import app

    monkeypatch.setattr(voz, "sintetizador_disponible", lambda: None)
    respuesta = TestClient(app).post("/api/agente/voz", json={"texto": "hola"})

    assert respuesta.status_code == 200
    assert respuesta.json()["success"] is False


def test_la_ruta_no_llama_al_proveedor_con_un_texto_vacio(monkeypatch):
    from fastapi.testclient import TestClient

    from api.main import app

    doble = SintetizadorFalso()
    monkeypatch.setattr(voz, "sintetizador_disponible", lambda: doble)
    cuerpo = TestClient(app).post("/api/agente/voz", json={"texto": "  "}).json()

    assert cuerpo["success"] is False
    assert doble.textos == []


# ----------------------------------------------------------------------
# La forma de la petición a cada proveedor
# ----------------------------------------------------------------------
# Se dobla la red, no el módulo. Lo que se comprueba es que la petición lleve el
# modelo, la voz y el formato correctos: si alguno falta, el proveedor responde
# un 400 que el usuario ve como "no se pudo generar la voz", sin más pistas.


class RespuestaHTTPFalsa:
    """Lo que devuelve `urlopen`: un contexto con `.read()`."""

    def __init__(self, cuerpo: bytes):
        self.cuerpo = cuerpo

    def __enter__(self):
        return self

    def __exit__(self, *_excepcion):
        return False

    def read(self) -> bytes:
        return self.cuerpo


def test_de_la_respuesta_de_google_se_saca_el_mime_y_el_audio():
    mime, audio = voz._audio_de_gemini({
        "candidates": [{"content": {"parts": [
            {"text": "ignorable"},
            {"inlineData": {"mimeType": MIME_PCM,
                            "data": base64.b64encode(PCM).decode("ascii")}},
        ]}}]
    })
    assert mime == MIME_PCM
    assert audio == PCM


def test_google_tambien_nombra_el_audio_en_snake_case():
    """
    La API alterna `inlineData` e `inline_data` según el cliente y la versión.
    Mirar solo uno deja el audio invisible y el error dice "respondió sin audio",
    que es exactamente lo contrario de lo que pasó.
    """
    mime, audio = voz._audio_de_gemini({
        "candidates": [{"content": {"parts": [
            {"inline_data": {"mime_type": "audio/L16;rate=16000",
                             "data": base64.b64encode(PCM).decode("ascii")}},
        ]}}]
    })
    assert mime == "audio/L16;rate=16000"
    assert audio == PCM


def test_una_respuesta_de_google_sin_audio_se_reporta_como_error():
    """
    Pasa de verdad: un filtro de seguridad devuelve `candidates` sin `parts`.
    Sin este `raise`, el código seguiría con un audio vacío y sonaría silencio.
    """
    with pytest.raises(RuntimeError):
        voz._audio_de_gemini({"candidates": [{"content": {"parts": []}}]})


def test_la_peticion_a_google_lleva_el_modelo_la_clave_y_la_voz(monkeypatch):
    vistas = {}

    def urlopen_falso(peticion, timeout=None):
        vistas["url"] = peticion.full_url
        vistas["cuerpo"] = json.loads(peticion.data.decode("utf-8"))
        vistas["timeout"] = timeout
        return RespuestaHTTPFalsa(json.dumps({
            "candidates": [{"content": {"parts": [
                {"inlineData": {"mimeType": MIME_PCM,
                                "data": base64.b64encode(PCM).decode("ascii")}}]}}]
        }).encode("utf-8"))

    monkeypatch.setattr(voz.urllib.request, "urlopen", urlopen_falso)

    hablar = voz.sintetizador_gemini("clave-google", modelo="gemini-tts-x", voz_pedida="Aoede")
    mime, audio = hablar("hay 12 cotizaciones pendientes")

    assert "gemini-tts-x:generateContent" in vistas["url"]
    assert "key=clave-google" in vistas["url"]
    assert vistas["cuerpo"]["generationConfig"]["responseModalities"] == ["AUDIO"]
    voz_pedida = (vistas["cuerpo"]["generationConfig"]["speechConfig"]
                  ["voiceConfig"]["prebuiltVoiceConfig"]["voiceName"])
    assert voz_pedida == "Aoede"
    assert vistas["cuerpo"]["contents"][0]["parts"][0]["text"] == "hay 12 cotizaciones pendientes"
    # El timeout no es decorativo: sin él una llamada colgada bloquea la función
    # serverless hasta que Vercel la mata, y el usuario no ve nada en 60 s.
    assert vistas["timeout"] == voz.TIMEOUT_S
    assert (mime, audio) == (MIME_PCM, PCM)


def test_la_peticion_a_groq_pide_wav_y_no_otro_formato(monkeypatch):
    """
    El formato importa: por defecto Groq devuelve otro contenedor, y `a_wav` lo
    dejaría pasar tal cual por no ser PCM. El `<audio>` no lo reproduciría.
    """
    vistas = {}

    class VozFalsa:
        @staticmethod
        def create(**argumentos):
            vistas.update(argumentos)
            return RespuestaHTTPFalsa(b"RIFFxxxxWAVE")

    class AudioFalso:
        speech = VozFalsa()

    class GroqFalso:
        def __init__(self, api_key=None):
            vistas["api_key"] = api_key
            self.audio = AudioFalso()

    monkeypatch.setattr("groq.Groq", GroqFalso)

    hablar = voz.sintetizador_groq("clave-groq", modelo="playai-x", voz_pedida="Atlas-PlayAI")
    mime, audio = hablar("hay 12 cotizaciones pendientes")

    assert vistas["api_key"] == "clave-groq"
    assert vistas["model"] == "playai-x"
    assert vistas["voice"] == "Atlas-PlayAI"
    assert vistas["response_format"] == "wav"
    assert vistas["input"] == "hay 12 cotizaciones pendientes"
    assert (mime, audio) == ("audio/wav", b"RIFFxxxxWAVE")
