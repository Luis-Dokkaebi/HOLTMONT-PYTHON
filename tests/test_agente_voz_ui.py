"""
El botón "Escuchar respuesta" del Agente de Consultas, recorrido como una persona.

`tests/test_agente_voz.py` cubre el backend: el recorte, la cabecera WAV y la
elección de proveedor. Aquí se comprueba lo único que esa suite no puede: que el
botón **existe junto a la respuesta**, que **pide la ruta** y que un fallo del
proveedor **se ve**.

Las tres fallan calladas, y por eso están:

- Un botón cuyo `@click` apunta a una función que no se exportó del `setup()` no
  da error de consola en Vue: el clic sencillamente no hace nada. Es el mismo
  fallo que tuvo `work_order_form` y por el que el módulo del agente ya lleva
  su prueba de mosaico.
- Si el audio no llega al `<audio>`, no suena nada. "No suena" y "el navegador
  tiene el volumen bajo" se ven idénticos desde la silla de quien lo usa.
- Si el aviso de error no se pinta, quien pulsa espera un audio que no va a
  llegar y no hay nada en pantalla que lo explique.

El proveedor de voz no se ejecuta: no hay clave en la suite y no la va a haber.
La respuesta se dobla en `fetch` —la frontera—, igual que en
`tests/test_agente_sql_ui.py`.
"""

from __future__ import annotations

import base64
import json

from playwright.sync_api import sync_playwright

BASE_URL = "http://localhost:8000"

ETIQUETA = "Agente de Consultas"

# Un WAV mínimo y válido: cabecera de 44 bytes y ni una muestra. Basta para que
# el navegador acepte el `src`; lo que se prueba es el cableado, no el sonido.
WAV = base64.b64encode(
    b"RIFF" + (36).to_bytes(4, "little") + b"WAVEfmt "
    + (16).to_bytes(4, "little") + (1).to_bytes(2, "little") + (1).to_bytes(2, "little")
    + (24000).to_bytes(4, "little") + (48000).to_bytes(4, "little")
    + (2).to_bytes(2, "little") + (16).to_bytes(2, "little")
    + b"data" + (0).to_bytes(4, "little")
).decode("ascii")

RESPUESTA = {
    "success": True,
    "respuesta": "HVAC tiene 12 actividades abiertas.",
    "sql": "SELECT departamento, COUNT(*) FROM tasks GROUP BY 1",
    "filas": [{"departamento": "HVAC", "count": 12}],
    "intentos": 1,
}


def _entrar(page, role: str, username: str) -> None:
    """Entra con la configuración real de esa cuenta, sin pasar por credenciales."""
    page.goto(BASE_URL)
    page.wait_for_selector(".login-card", state="visible", timeout=15000)
    page.evaluate(
        """async ([role, username]) => {
            const app = document.querySelector('#app').__vue_app__._instance.proxy;
            const url = `/api/config?role=${role}&username=${username}`;
            app.config = await fetch(url).then(r => r.json());
            app.currentRole = role;
            app.currentUsername = username;
            app.isLoggedIn = true;
        }""",
        [role, username],
    )
    page.wait_for_selector(".nav-item", timeout=15000)


def _doblar(page, ruta: str, cuerpo: dict, registro: list = None) -> None:
    """Sustituye una ruta del agente sin tocar el resto de la red."""
    def responder(peticion):
        if registro is not None:
            registro.append(peticion.request.post_data)
        peticion.fulfill(status=200, content_type="application/json",
                         body=json.dumps(cuerpo))

    page.route(f"**{ruta}", responder)


def _preguntar(page) -> None:
    """Abre el módulo y deja una respuesta pintada en pantalla."""
    _entrar(page, "ADMIN", "LUIS_CARLOS")
    page.click(f".nav-item:has-text('{ETIQUETA}')")
    page.fill("#agentePregunta", "¿cuántas actividades abiertas hay por área?")
    page.click("#agenteConsultarBtn")
    page.wait_for_selector("#agenteRespuesta", timeout=15000)


def test_el_boton_de_voz_aparece_junto_a_la_respuesta_y_no_antes():
    """
    Antes de preguntar no hay nada que leer, así que no hay botón que ofrecer.

    Un botón que se puede pulsar sin respuesta gasta una llamada al proveedor
    para sintetizar la cadena vacía.
    """
    with sync_playwright() as p:
        navegador = p.chromium.launch(headless=True)
        page = navegador.new_page(viewport={"width": 1500, "height": 950})
        try:
            _doblar(page, "/api/agente/consulta", RESPUESTA)
            _entrar(page, "ADMIN", "LUIS_CARLOS")
            page.click(f".nav-item:has-text('{ETIQUETA}')")
            page.wait_for_selector("#agentePregunta", timeout=15000)
            assert page.locator("#agenteVozBtn").count() == 0

            page.fill("#agentePregunta", "¿cuántas actividades abiertas hay por área?")
            page.click("#agenteConsultarBtn")
            page.wait_for_selector("#agenteRespuesta", timeout=15000)
            assert page.locator("#agenteVozBtn").count() == 1
        finally:
            navegador.close()


def test_al_pulsar_se_pide_la_voz_del_texto_que_esta_en_pantalla():
    """
    Lo que se manda a leer es la respuesta visible, no la pregunta ni las filas.

    Es la defensa entera de este módulo: las filas traen `comentarios` y
    `concepto`, que captura cualquiera en el Tracker. Si lo que viajara fueran
    las filas, bastaría con escribir en una celda para hacer hablar a la bocina.
    """
    with sync_playwright() as p:
        navegador = p.chromium.launch(headless=True)
        page = navegador.new_page(viewport={"width": 1500, "height": 950})
        try:
            enviado = []
            _doblar(page, "/api/agente/consulta", RESPUESTA)
            _doblar(page, "/api/agente/voz",
                    {"success": True, "audio": WAV, "mime": "audio/wav",
                     "texto": RESPUESTA["respuesta"], "recortado": False},
                    registro=enviado)

            _preguntar(page)
            page.click("#agenteVozBtn")
            page.wait_for_selector("#agenteAudio audio", timeout=15000)

            assert json.loads(enviado[0])["texto"] == "HVAC tiene 12 actividades abiertas."
            assert page.get_attribute("#agenteAudio audio", "src").startswith(
                "data:audio/wav;base64,")
        finally:
            navegador.close()


def test_si_la_respuesta_no_cupo_entera_se_dice_en_pantalla():
    """
    Escuchar media respuesta creyéndola completa es peor que no escucharla.

    El backend lo marca con `recortado`; si el frontend lo ignora, el dato se
    pierde justo donde importa.
    """
    with sync_playwright() as p:
        navegador = p.chromium.launch(headless=True)
        page = navegador.new_page(viewport={"width": 1500, "height": 950})
        try:
            _doblar(page, "/api/agente/consulta", RESPUESTA)
            _doblar(page, "/api/agente/voz",
                    {"success": True, "audio": WAV, "mime": "audio/wav",
                     "texto": "HVAC tiene", "recortado": True})

            _preguntar(page)
            page.click("#agenteVozBtn")
            page.wait_for_selector("#agenteVozRecortada", timeout=15000)
            assert "solo el principio" in page.inner_text("#agenteVozRecortada")
        finally:
            navegador.close()


def test_un_fallo_del_proveedor_se_dice_y_no_se_deja_un_reproductor_mudo():
    """
    Sin clave no hay audio, y hay que verlo. Un `<audio>` vacío en pantalla se
    pulsa, no suena, y nadie sabe si falta la clave o falla el navegador.
    """
    with sync_playwright() as p:
        navegador = p.chromium.launch(headless=True)
        page = navegador.new_page(viewport={"width": 1500, "height": 950})
        try:
            _doblar(page, "/api/agente/consulta", RESPUESTA)
            _doblar(page, "/api/agente/voz",
                    {"success": False,
                     "message": "La lectura en voz alta no está configurada en este despliegue: "
                                "falta GEMINI_API_KEY (voz en español) o GROQ_API_KEY."})

            _preguntar(page)
            page.click("#agenteVozBtn")
            page.wait_for_selector("#agenteAvisoVoz", timeout=15000)

            assert "GEMINI_API_KEY" in page.inner_text("#agenteAvisoVoz")
            assert page.locator("#agenteAudio").count() == 0
        finally:
            navegador.close()


def test_una_consulta_nueva_se_lleva_el_audio_de_la_anterior():
    """
    Un audio viejo junto a una respuesta nueva se escucha como si fuera de esta.

    Es el mismo criterio que ya seguía el diagnóstico en `consultarAgente`, y el
    error que produce no es visible: el reproductor se ve perfectamente normal.
    """
    with sync_playwright() as p:
        navegador = p.chromium.launch(headless=True)
        page = navegador.new_page(viewport={"width": 1500, "height": 950})
        try:
            _doblar(page, "/api/agente/consulta", RESPUESTA)
            _doblar(page, "/api/agente/voz",
                    {"success": True, "audio": WAV, "mime": "audio/wav",
                     "texto": RESPUESTA["respuesta"], "recortado": False})

            _preguntar(page)
            page.click("#agenteVozBtn")
            page.wait_for_selector("#agenteAudio audio", timeout=15000)

            page.fill("#agentePregunta", "¿y cuántas cerradas?")
            page.click("#agenteConsultarBtn")
            page.wait_for_selector("#agenteRespuesta", timeout=15000)
            assert page.locator("#agenteAudio").count() == 0
        finally:
            navegador.close()
