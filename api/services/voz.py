"""
La voz del Agente de Consultas: convierte en audio la respuesta ya redactada.

Existe por una petición concreta —que la respuesta del agente se **oiga** y no
solo se lea— y está escrito con la misma forma que `agente_sql.py`, no con otra:
el proveedor de voz **se inyecta**, igual que ahí se inyectan el LLM y la
ejecución del SQL. Así el módulo se prueba entero sin salir a internet y sin
una clave, que es la única manera de que estas pruebas corran en CI.

**Qué se lee en voz alta, y qué no.** Solo la prosa que redactó el modelo
(`agente_sql.PROMPT_RESPUESTA`). Nunca el resultado crudo de la base. La razón
está escrita en `agente_sql_esquemas.py`: `comentarios`, `comentarios_semana` y
`concepto` son campos de texto libre que captura cualquier usuario del Tracker,
y quien quiera puede escribir ahí lo que se le antoje. Leer esas celdas por una
bocina en un congreso es exactamente el fallo que no se puede deshacer.

Este módulo aporta dos mitigaciones —el tope de caracteres y el filtro de
caracteres de control— y conviene decir en voz alta que **no son la garantía**.
La garantía es que quien llama manda `agente.respuesta`. Igual que con los
correos del agente (`agente_sql_correo.py`), la última defensa es que una
persona ve el texto en pantalla antes de que suene.

**Por qué dos proveedores.** Las voces de `playai-tts` (Groq) están entrenadas
en inglés y leen el español con acento; las de Gemini son multilingües. La
respuesta del agente es en español, así que Google va primero y Groq queda de
respaldo para los despliegues que solo tienen esa clave. `TTS_PROVEEDOR` fuerza
uno de los dos cuando haga falta decidir a mano.

**Por qué el WAV se arma aquí.** Gemini no devuelve un archivo de audio: devuelve
PCM crudo de 16 bits (`audio/L16;codec=pcm;rate=24000`). Ningún `<audio>` del
navegador reproduce eso. Sin la cabecera de 44 bytes que le pone `envolver_wav`,
el botón "no hace nada" y no hay error en ninguna consola.
"""

from __future__ import annotations

import base64
import json
import os
import re
import struct
import urllib.request
from typing import Any, Callable, Dict, Iterator, Optional, Sequence, Tuple

# El contrato del proveedor: recibe texto y devuelve `(mime, audio)`. Es lo que
# se dobla en las pruebas y lo que implementan las dos fábricas de abajo.
Sintetizador = Callable[[str], Tuple[str, bytes]]

# Techo de lo que se manda a leer. No es cosmético: se paga por carácter, la
# latencia crece con el texto, y una respuesta del agente que se pase de aquí
# ya no es una respuesta hablada sino una lectura de informe.
TOPE_CARACTERES = 1200

# La que documenta Google para su salida de PCM. Adivinarla mal no falla con un
# error: suena a cámara lenta o a ardilla, que es peor porque parece un bug del
# audio y no de la configuración.
FRECUENCIA_POR_DEFECTO = 24000

# --- Configuración por entorno ---------------------------------------------
# Misma lección que `api/modelos_llm.py`: un identificador de modelo **caduca**.
# El proveedor lo retira y desde ese instante cada llamada responde 404 con una
# clave perfectamente válida. Poder cambiarlo sin desplegar es la diferencia
# entre un renglón y esperar un despliegue.
ENV_PROVEEDOR = "TTS_PROVEEDOR"
ENV_MODELO_GEMINI = "TTS_MODELO_GEMINI"
ENV_VOZ_GEMINI = "TTS_VOZ_GEMINI"
ENV_MODELO_GROQ = "TTS_MODELO_GROQ"
ENV_VOZ_GROQ = "TTS_VOZ_GROQ"

MODELO_GEMINI = "gemini-2.5-flash-preview-tts"
VOZ_GEMINI = "Kore"
MODELO_GROQ = "playai-tts"
VOZ_GROQ = "Celeste-PlayAI"

GEMINI_TTS_BASE = "https://generativelanguage.googleapis.com/v1beta/models"
TIMEOUT_S = 30

MENSAJE_SIN_PROVEEDOR = (
    "La lectura en voz alta no está configurada en este despliegue: falta "
    "GEMINI_API_KEY (voz en español) o GROQ_API_KEY (voz en inglés). El agente "
    "sigue respondiendo por escrito."
)

MENSAJE_VACIO = "No hay nada que leer: el agente todavía no respondió."

MENSAJE_AUDIO_VACIO = (
    "El proveedor de voz respondió sin audio. No se reproduce nada en vez de "
    "sonar en silencio, que es indistinguible de un fallo del navegador."
)

# Nulos, campanas y demás basura de captura. Rompen a los proveedores y no se
# pueden pronunciar. El salto de línea y el tabulador se quedan: marcan pausa.
_CONTROL = re.compile(r"[\x00-\x08\x0b\x0c\x0e-\x1f\x7f]")


# ----------------------------------------------------------------------
# Preparación del texto: funciones puras
# ----------------------------------------------------------------------


def limpiar(texto: str) -> str:
    """El texto sin caracteres de control y sin espacios sobrantes en los bordes."""
    return _CONTROL.sub(" ", str(texto or "")).strip()


def recortar(texto: str, tope: int = TOPE_CARACTERES) -> str:
    """
    El texto limpio, cortado al tope y **sin partir una palabra**.

    Un corte a mitad de palabra se oye como un balbuceo y hace dudar de todo lo
    que se dijo antes. Cuando no hay ningún espacio donde cortar —una sola
    palabra larguísima— se corta igual: pasarse del tope no es una opción.
    """
    limpio = limpiar(texto)
    if len(limpio) <= tope:
        return limpio
    corte = limpio[:tope]
    ultimo_espacio = corte.rfind(" ")
    return corte[:ultimo_espacio].rstrip() if ultimo_espacio > 0 else corte


def frecuencia_de(mime: str) -> int:
    """
    La frecuencia de muestreo declarada en el mime, o la de por defecto.

    Gemini la manda dentro del propio tipo: `audio/L16;codec=pcm;rate=24000`.
    """
    encontrada = re.search(r"rate=(\d+)", str(mime or ""))
    return int(encontrada.group(1)) if encontrada else FRECUENCIA_POR_DEFECTO


def envolver_wav(pcm: bytes, frecuencia: int, canales: int = 1, bits: int = 16) -> bytes:
    """
    El PCM con la cabecera WAV de 44 bytes delante, para que un `<audio>` lo lea.

    Los tamaños se calculan, no se fijan: una cabecera que declara una longitud
    distinta de la real se reproduce truncada o con un chasquido al final.
    """
    bloque = canales * bits // 8
    cabecera = b"".join((
        b"RIFF", struct.pack("<I", 36 + len(pcm)), b"WAVE",
        b"fmt ", struct.pack("<IHHIIHH", 16, 1, canales, frecuencia,
                             frecuencia * bloque, bloque, bits),
        b"data", struct.pack("<I", len(pcm)),
    ))
    return cabecera + pcm


def a_wav(mime: str, audio: bytes) -> bytes:
    """
    El audio listo para reproducir, venga como venga del proveedor.

    Groq ya devuelve un WAV completo; Gemini, PCM crudo. Poner una segunda
    cabecera sobre un WAV lo deja irreproducible, así que se comprueba antes.
    """
    if str(mime or "").lower().startswith("audio/wav") or audio[:4] == b"RIFF":
        return audio
    return envolver_wav(audio, frecuencia_de(mime))


# ----------------------------------------------------------------------
# El orquestador. Nunca lanza.
# ----------------------------------------------------------------------


def sintetizar(texto: str, sintetizador: Optional[Sintetizador]) -> Dict[str, Any]:
    """
    Convierte `texto` en audio con el proveedor que se le pase.

    Sin proveedor **no se fabrica un audio vacío**: se dice qué falta. Es el
    mismo criterio de `agente_sql.ejecutar` con el LLM — un WAV mudo y un fallo
    del navegador se ven exactamente igual desde el otro lado de la pantalla.

    Devuelve también `texto` y `recortado`: quien escucha tiene derecho a saber
    que oyó un trozo. Un resumen a medias presentado como completo es el fallo
    caro de este módulo.
    """
    completo = limpiar(texto)
    leible = recortar(completo)
    if not leible:
        return {"success": False, "message": MENSAJE_VACIO}

    if sintetizador is None:
        return {"success": False, "message": MENSAJE_SIN_PROVEEDOR}

    try:
        mime, audio = sintetizador(leible)
    except Exception as exc:
        return {"success": False, "message": f"No se pudo generar la voz ({exc})."}

    if not audio:
        return {"success": False, "message": MENSAJE_AUDIO_VACIO}

    return {
        "success": True,
        "audio": base64.b64encode(a_wav(mime, audio)).decode("ascii"),
        "mime": "audio/wav",
        "texto": leible,
        "recortado": len(leible) < len(completo),
    }


# ----------------------------------------------------------------------
# Los proveedores. Se construyen aquí y se inyectan arriba.
# ----------------------------------------------------------------------


def _clave(alias: Sequence[str]) -> str:
    """
    El primer alias del entorno con valor, o cadena vacía.

    Los nombres vienen de `api/paperclip_agents.py` y no se reescriben aquí: en
    el despliegue real la clave de Google está puesta como `Gemini_Key`, y las
    variables de entorno distinguen mayúsculas. Leer solo `GEMINI_API_KEY` la
    deja invisible aunque se vea puesta en el panel (commit 50c7330).
    """
    for nombre in alias:
        valor = (os.environ.get(nombre) or "").strip()
        if valor:
            return valor
    return ""


def _partes_de(cuerpo: Dict[str, Any]) -> Iterator[Dict[str, Any]]:
    """Las partes de todos los candidatos, en orden, sin reventar si faltan."""
    for candidato in cuerpo.get("candidates") or []:
        yield from (candidato.get("content") or {}).get("parts") or []


def _datos_en_linea(parte: Dict[str, Any]) -> Dict[str, Any]:
    """
    El bloque de audio de una parte, se llame como se llame.

    La API alterna `inlineData` e `inline_data` según la versión y el cliente.
    Mirar solo uno de los dos deja el audio invisible, y el error resultante
    ("respondió sin audio") dice justo lo contrario de lo que pasó.
    """
    return parte.get("inlineData") or parte.get("inline_data") or {}


def _audio_de_gemini(cuerpo: Dict[str, Any]) -> Tuple[str, bytes]:
    """
    El `(mime, audio)` que viene dentro de la respuesta de Gemini.

    Lanza cuando no hay audio en vez de devolver bytes vacíos: pasa de verdad
    —un filtro de seguridad devuelve `candidates` sin `parts`— y un audio vacío
    se reproduce como silencio, indistinguible de un fallo del navegador.
    """
    for parte in _partes_de(cuerpo):
        datos = _datos_en_linea(parte)
        if datos.get("data"):
            mime = datos.get("mimeType") or datos.get("mime_type") or ""
            return str(mime), base64.b64decode(datos["data"])
    raise RuntimeError("Gemini respondió sin audio")


def sintetizador_gemini(clave: str, modelo: str = "", voz_pedida: str = "") -> Sintetizador:
    """
    Un sintetizador contra Gemini. Voces multilingües: lee español sin acento.

    Va por `urllib` y no por el SDK de Google por lo mismo que
    `tracker_store.call_gemini`: es una sola llamada HTTP y la biblioteca
    estándar ya la hace, así que no se añade una dependencia al despliegue.
    """
    nombre_modelo = modelo or os.environ.get(ENV_MODELO_GEMINI, "").strip() or MODELO_GEMINI
    nombre_voz = voz_pedida or os.environ.get(ENV_VOZ_GEMINI, "").strip() or VOZ_GEMINI

    def hablar(texto: str) -> Tuple[str, bytes]:
        cuerpo = json.dumps({
            "contents": [{"parts": [{"text": texto}]}],
            "generationConfig": {
                "responseModalities": ["AUDIO"],
                "speechConfig": {
                    "voiceConfig": {"prebuiltVoiceConfig": {"voiceName": nombre_voz}},
                },
            },
        }).encode("utf-8")
        peticion = urllib.request.Request(
            f"{GEMINI_TTS_BASE}/{nombre_modelo}:generateContent?key={clave}",
            data=cuerpo, headers={"Content-Type": "application/json"}, method="POST")
        with urllib.request.urlopen(peticion, timeout=TIMEOUT_S) as respuesta:
            return _audio_de_gemini(json.loads(respuesta.read().decode("utf-8")))

    hablar.proveedor = "gemini"
    hablar.modelo = nombre_modelo
    hablar.voz = nombre_voz
    return hablar


def sintetizador_groq(clave: str, modelo: str = "", voz_pedida: str = "") -> Sintetizador:
    """
    Un sintetizador contra Groq. Devuelve WAV ya armado.

    Sus voces están entrenadas en inglés: leen el español de forma inteligible
    pero con acento marcado. Queda de respaldo para el despliegue que solo tenga
    esta clave, que ya es la del resto de los agentes del proyecto.
    """
    nombre_modelo = modelo or os.environ.get(ENV_MODELO_GROQ, "").strip() or MODELO_GROQ
    nombre_voz = voz_pedida or os.environ.get(ENV_VOZ_GROQ, "").strip() or VOZ_GROQ

    def hablar(texto: str) -> Tuple[str, bytes]:
        from groq import Groq

        respuesta = Groq(api_key=clave).audio.speech.create(
            model=nombre_modelo, voice=nombre_voz, response_format="wav", input=texto)
        return "audio/wav", respuesta.read()

    hablar.proveedor = "groq"
    hablar.modelo = nombre_modelo
    hablar.voz = nombre_voz
    return hablar


def sintetizador_disponible() -> Optional[Sintetizador]:
    """
    El proveedor de voz configurado, o `None` si no hay ninguno.

    Devolver `None` en vez de lanzar es el criterio de
    `agente_sql.llm_disponible()`: la falta de clave limita lo que el módulo
    hace, no tumba la aplicación.

    Cuando `TTS_PROVEEDOR` pide uno concreto y ese no tiene clave, se devuelve
    `None` en vez de caer al otro. Usar el otro en silencio es peor que no
    sonar: se pidió una voz y saldría otra sin decirlo.
    """
    from api.paperclip_agents import ALIAS_CLAVE_GEMINI, ALIAS_CLAVE_GROQ

    pedido = os.environ.get(ENV_PROVEEDOR, "").strip().lower()
    clave_google = _clave(ALIAS_CLAVE_GEMINI)
    clave_groq = _clave(ALIAS_CLAVE_GROQ)

    if pedido == "gemini":
        return sintetizador_gemini(clave_google) if clave_google else None
    if pedido == "groq":
        return sintetizador_groq(clave_groq) if clave_groq else None
    if clave_google:
        return sintetizador_gemini(clave_google)
    if clave_groq:
        return sintetizador_groq(clave_groq)
    return None
