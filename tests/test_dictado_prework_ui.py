"""
El micrófono de la Pre Work Order, recorrido como lo recorre una persona.

La cuenta `PREWORK_ORDER` entra directo a este formulario y su única forma
práctica de capturar el levantamiento es hablando: el recorrido con el cliente
es caminando y no da tiempo de teclear (es lo que dice la propia tarjeta de
lógica de la pantalla). El botón del micrófono es, por tanto, la entrada
principal de datos de esa cuenta, no un adorno.

Estaba muerto. El `onclick` del botón solo hacía
`document.getElementById('campoConcepto').focus()`: ponía el cursor en el
recuadro y nada más. `toggleVoiceRecording()` —la función que graba, sube el
audio y pega la transcripción— seguía definida más abajo en el archivo pero ya
no la llamaba nadie.

Ese fallo es invisible desde la silla de quien lo usa: el cursor parpadea en el
campo, así que parece que el sistema "está escuchando". La persona habla, no
aparece texto, y no hay ningún error en pantalla que lo explique. Por eso las
cuatro pruebas de aquí son de navegador y no de unidad: lo que se rompió no fue
una regla de negocio, fue el cable entre el botón y la función.

Qué cubre cada una:

- que el botón **pida el micrófono** en vez de solo mover el cursor;
- que el texto transcrito llegue al modelo de Vue y no solo al DOM (escribir
  `textarea.value` sin avisar a Vue deja el dato fuera de lo que se guarda);
- que el audio viaje con el **formato real** del navegador — Safari graba en
  MP4 y etiquetarlo `.webm` hace que Whisper lo rechace;
- que un fallo del servidor **se vea**, en vez de dejar a la persona esperando
  un texto que no va a llegar.

El proveedor de transcripción no se ejecuta: no hay clave Groq en la suite y no
la va a haber. La respuesta se dobla en `fetch` —la frontera—, igual que en
`tests/test_agente_sql_ui.py` y `tests/test_agente_voz_ui.py`.
"""

from __future__ import annotations

import json
import os
import pathlib

import pytest
from playwright.sync_api import sync_playwright

BASE_URL = "http://localhost:8000"

CAPTURAS = pathlib.Path(__file__).resolve().parent.parent / "verification" / "screenshots"

RUTA_TRANSCRIPCION = "**/api/transcribe_and_analyze"

# Lo que "dice" la persona en la prueba. Lleva la palabra "error" a propósito:
# el backend decidía si había fallado buscando esa subcadena en el texto
# devuelto, así que una frase legítima de taller ("revisar el error del
# tablero") se tomaba por un fallo de transcripción.
TEXTO_DICTADO = "Revisar el error del tablero principal y cotizar dos contactores"


def _grabadora_falsa(mime: str = "audio/webm") -> str:
    """Sustituye micrófono y grabadora del navegador por dobles observables.

    No se pide permiso de micrófono real: en un navegador sin cabeza no hay
    dispositivo que conceder, y lo que se prueba es el cableado del botón, no
    el hardware. Todo lo que hacen los dobles queda anotado en
    `window.__grabacion` para poder afirmar sobre ello.
    """
    return """
    (() => {
        window.__grabacion = { solicitudes: 0, iniciadas: 0, pistasCerradas: 0 };

        const pista = { stop: () => { window.__grabacion.pistasCerradas++; } };
        const stream = { getTracks: () => [pista] };

        Object.defineProperty(navigator, 'mediaDevices', {
            configurable: true,
            value: {
                getUserMedia: async () => {
                    window.__grabacion.solicitudes++;
                    return stream;
                }
            }
        });

        class GrabadoraFalsa {
            constructor(flujo) {
                this.stream = flujo;
                this.state = 'inactive';
                this.mimeType = '__MIME__';
                this.ondataavailable = null;
                this.onstop = null;
            }
            start() {
                this.state = 'recording';
                window.__grabacion.iniciadas++;
            }
            stop() {
                this.state = 'inactive';
                const datos = new Blob(['audio-de-prueba'], { type: this.mimeType });
                if (this.ondataavailable) this.ondataavailable({ data: datos });
                if (this.onstop) this.onstop();
            }
        }
        GrabadoraFalsa.isTypeSupported = () => true;
        window.MediaRecorder = GrabadoraFalsa;
    })();
    """.replace("__MIME__", mime)


def _abrir_formulario(page) -> None:
    """Entra a la Pre Work Order sin pasar por credenciales reales."""
    page.goto(BASE_URL)
    page.wait_for_selector(".login-card", state="visible", timeout=15000)
    page.evaluate(
        "() => { const app = document.querySelector('#app').__vue_app__._instance.proxy;"
        " app.isLoggedIn = true; app.currentView = 'WORKORDER_FORM'; }")
    page.wait_for_selector("#campoConcepto", timeout=15000)


def _doblar_transcripcion(page, cuerpo: dict, registro: list = None) -> None:
    """Responde la ruta de transcripción sin tocar el resto de la red."""
    def responder(peticion):
        if registro is not None:
            registro.append(peticion.request.post_data or "")
        peticion.fulfill(status=200, content_type="application/json",
                         body=json.dumps(cuerpo))

    page.route(RUTA_TRANSCRIPCION, responder)


def _microfono(page):
    return page.locator("button[title='Dictar voz a texto']")


def _capturar(page, nombre: str) -> None:
    """Deja la evidencia del arreglo en verification/screenshots."""
    os.makedirs(CAPTURAS, exist_ok=True)
    page.screenshot(path=str(CAPTURAS / nombre), full_page=False)


def _concepto_en_vue(page) -> str:
    return page.evaluate(
        "() => document.querySelector('#app').__vue_app__._instance.proxy"
        ".workorderData.conceptoDesc || ''")


@pytest.fixture()
def pagina():
    with sync_playwright() as p:
        navegador = p.chromium.launch(headless=True)
        page = navegador.new_page(viewport={"width": 1500, "height": 950})
        try:
            yield page
        finally:
            navegador.close()


def test_el_boton_del_microfono_pide_el_microfono_y_no_solo_mueve_el_cursor(pagina):
    """El fallo exacto: el botón enfocaba el recuadro y jamás grababa nada."""
    pagina.add_init_script(_grabadora_falsa())
    _abrir_formulario(pagina)

    _microfono(pagina).click()
    pagina.wait_for_timeout(500)

    estado = pagina.evaluate("() => window.__grabacion")
    assert estado["solicitudes"] == 1, (
        "El botón del micrófono no pidió acceso al micrófono. Con el cursor "
        "puesto en el campo la pantalla parece estar escuchando, y no lo está."
    )
    assert estado["iniciadas"] == 1, "Se pidió el micrófono pero no se empezó a grabar."


def test_el_texto_dictado_llega_al_modelo_y_no_solo_al_recuadro(pagina):
    """Escribir en el DOM sin avisar a Vue deja el dictado fuera de lo que se guarda."""
    pagina.add_init_script(_grabadora_falsa())
    _abrir_formulario(pagina)
    _doblar_transcripcion(pagina, {"success": True, "transcription": TEXTO_DICTADO,
                                   "data": {}})

    _microfono(pagina).click()      # empieza a grabar
    pagina.wait_for_timeout(300)
    _microfono(pagina).click()      # detiene y sube el audio

    pagina.wait_for_function(
        "() => document.querySelector('#app').__vue_app__._instance.proxy"
        ".workorderData.conceptoDesc.length > 0", timeout=15000)

    assert TEXTO_DICTADO in _concepto_en_vue(pagina), (
        "La transcripción no llegó a workorderData.conceptoDesc: lo que se "
        "guarda en la Work Order saldría vacío aunque la pantalla muestre texto."
    )
    assert TEXTO_DICTADO in pagina.input_value("#campoConcepto")
    _capturar(pagina, "prework_dictado_en_la_descripcion.png")


def test_el_audio_viaja_con_el_formato_que_el_navegador_grabo(pagina):
    """Safari graba MP4. Etiquetarlo `.webm` hace que Whisper lo rechace."""
    pagina.add_init_script(_grabadora_falsa(mime="audio/mp4"))
    _abrir_formulario(pagina)

    enviado: list = []
    _doblar_transcripcion(pagina, {"success": True, "transcription": TEXTO_DICTADO,
                                   "data": {}}, registro=enviado)

    _microfono(pagina).click()
    pagina.wait_for_timeout(300)
    _microfono(pagina).click()

    pagina.wait_for_function(
        "() => document.querySelector('#app').__vue_app__._instance.proxy"
        ".workorderData.conceptoDesc.length > 0", timeout=15000)

    cuerpo = enviado[0]
    assert 'filename="audio.mp4"' in cuerpo, (
        f"El audio se subió con un nombre que no corresponde a lo grabado: {cuerpo[:400]}")
    assert "webm" not in cuerpo, (
        "Se sigue etiquetando el audio como webm sin importar lo que grabó el navegador.")


def test_un_fallo_del_servidor_se_dice_en_pantalla(pagina):
    """Sin aviso, la persona espera un texto que no va a llegar."""
    pagina.add_init_script(_grabadora_falsa())
    _abrir_formulario(pagina)
    _doblar_transcripcion(pagina, {"success": False, "message": "Falta GROQ_API_KEY"})

    _microfono(pagina).click()
    pagina.wait_for_timeout(300)
    _microfono(pagina).click()

    pagina.wait_for_selector(".swal2-popup .swal2-title", timeout=15000)
    pagina.wait_for_function(
        "() => /error/i.test(document.querySelector('.swal2-popup').innerText)",
        timeout=15000)

    texto = pagina.locator(".swal2-popup").inner_text()
    assert "GROQ_API_KEY" in texto, (
        f"El aviso no dice qué falló; solo se ve un error genérico: {texto!r}")
    assert _concepto_en_vue(pagina) == "", "Un fallo no debe ensuciar la descripción."


# --------------------------------------------------------------------------- #
# La otra ruta de voz: la grabadora nativa del teléfono
# --------------------------------------------------------------------------- #
#
# En móvil `toggleVoiceRecording` no usa `getUserMedia` —pedir el micrófono
# desde una pestaña en un teléfono es una carrera de permisos que casi nadie
# gana— sino que abre la grabadora del sistema a través del `<input type=file>`
# oculto. Es la ruta que usa de verdad quien está en obra, y pasa por otra
# función (`enviarAudioAGemini`), así que se recorre aparte.


def test_el_audio_del_selector_llega_a_la_descripcion(pagina, tmp_path):
    """La ruta del teléfono: grabadora nativa → selector oculto → descripción."""
    _abrir_formulario(pagina)
    _doblar_transcripcion(pagina, {"success": True, "transcription": TEXTO_DICTADO,
                                   "data": {}})

    audio = tmp_path / "grabacion.m4a"
    audio.write_bytes(b"audio-de-prueba")
    pagina.set_input_files("#audioInputGemini", str(audio))

    pagina.wait_for_function(
        "() => document.querySelector('#app').__vue_app__._instance.proxy"
        ".workorderData.conceptoDesc.length > 0", timeout=15000)

    assert TEXTO_DICTADO in _concepto_en_vue(pagina)


def test_el_selector_se_vacia_para_que_la_segunda_grabacion_no_se_pierda(pagina, tmp_path):
    """`change` solo se dispara cuando la selección cambia.

    La grabadora nativa de Android reutiliza el mismo nombre de archivo
    temporal, así que la segunda grabación seguida no disparaba nada: desde la
    pantalla parecía que el botón había dejado de responder.
    """
    _abrir_formulario(pagina)
    _doblar_transcripcion(pagina, {"success": True, "transcription": TEXTO_DICTADO,
                                   "data": {}})

    audio = tmp_path / "grabacion.m4a"
    audio.write_bytes(b"audio-de-prueba")
    pagina.set_input_files("#audioInputGemini", str(audio))

    pagina.wait_for_function(
        "() => document.getElementById('audioInputGemini').value === ''", timeout=15000)
