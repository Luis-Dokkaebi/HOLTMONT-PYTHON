"""
El puente con el editor 3D, visto desde la pantalla.

Lo que se comprueba aquí es lo que no se veía cuando el plano 3D salía en
negro: que el diseño se manda **cuando el editor avisa que escucha**, y que si
el editor lo rechaza o lo dibuja incompleto, la pantalla lo dice.

Antes, el diseño se mandaba tras un retraso fijo y la respuesta del editor se
ignoraba. Si el mensaje llegaba antes de tiempo, o si el editor no sabía
dibujar lo que le llegaba, el resultado era el mismo: un lienzo oscuro, sin
aviso, con la interfaz diciendo que todo estaba bien.
"""

from __future__ import annotations

import json

from playwright.sync_api import sync_playwright

BASE_URL = "http://localhost:8000"

# Una escena mínima pero válida: basta para comprobar el trasiego de mensajes.
ESCENA = {
    "nodes": {
        "site_prueba": {
            "object": "node", "id": "site_prueba", "type": "site", "parentId": None,
            "visible": True, "metadata": {},
            "polygon": {"type": "polygon", "points": [[-5, -5], [5, -5], [5, 5], [-5, 5]]},
            "children": [],
        }
    },
    "rootNodeIds": ["site_prueba"],
}


def _abrir_editor_3d(page, escena=ESCENA):
    """Entra a la vista del editor con un diseño ya cargado y un iframe inocuo."""
    page.goto(BASE_URL)
    page.wait_for_selector(".login-card", state="visible", timeout=15000)
    page.evaluate(
        """(escena) => {
            const app = document.querySelector('#app').__vue_app__._instance.proxy;
            app.isLoggedIn = true;
            // El editor real vive en Vercel: aquí solo hace falta un iframe con
            // `contentWindow`, porque lo que se prueba es el intercambio de
            // mensajes de este lado.
            app.pascalEditorUrl = 'about:blank';
            app.saved3DProjectData = escena;
            app.currentView = 'PASCAL_DESIGNER';
        }""",
        escena,
    )
    page.wait_for_selector("#pascal-editor-iframe", timeout=15000)
    # Registra lo que se le manda al iframe sin depender de que el editor cargue.
    page.evaluate(
        """() => {
            const iframe = document.getElementById('pascal-editor-iframe');
            window.__mensajesAlEditor = [];
            iframe.contentWindow.postMessage = (payload) => {
                window.__mensajesAlEditor.push(JSON.parse(JSON.stringify(payload)));
            };
        }"""
    )


def _enviados(page):
    return page.evaluate("() => window.__mensajesAlEditor || []")


def test_el_diseno_se_manda_cuando_el_editor_avisa_que_escucha():
    """`PASCAL_READY` es la señal: no se adivina cuánto tarda en arrancar."""
    with sync_playwright() as p:
        navegador = p.chromium.launch(headless=True)
        page = navegador.new_page(viewport={"width": 1500, "height": 950})
        try:
            _abrir_editor_3d(page)
            assert _enviados(page) == [], "no debería mandarse nada antes del aviso"

            page.evaluate("() => window.postMessage({ type: 'PASCAL_READY' }, '*')")
            page.wait_for_function("() => (window.__mensajesAlEditor || []).length > 0",
                                   timeout=5000)

            mensajes = _enviados(page)
            assert mensajes[0]["type"] == "HOLTMONT_3D_IMPORT"
            # El editor lee `projectData.nodes`: con otra clave se queda vacío.
            assert "site_prueba" in mensajes[0]["projectData"]["nodes"]
        finally:
            navegador.close()


def test_un_diseno_en_texto_llega_al_editor_como_objeto():
    """
    El agente devuelve el diseño serializado (`json.dumps`). Si viaja como
    cadena, el editor no encuentra `projectData.nodes` y no dibuja nada.
    """
    with sync_playwright() as p:
        navegador = p.chromium.launch(headless=True)
        page = navegador.new_page(viewport={"width": 1500, "height": 950})
        try:
            _abrir_editor_3d(page, escena=json.dumps(ESCENA))
            page.evaluate("() => window.postMessage({ type: 'PASCAL_READY' }, '*')")
            page.wait_for_function("() => (window.__mensajesAlEditor || []).length > 0",
                                   timeout=5000)

            enviado = _enviados(page)[0]["projectData"]
            assert isinstance(enviado, dict) and "site_prueba" in enviado["nodes"]
        finally:
            navegador.close()


def test_si_el_editor_rechaza_el_diseno_la_pantalla_lo_dice():
    """El síntoma del bug era justo la ausencia de este aviso."""
    with sync_playwright() as p:
        navegador = p.chromium.launch(headless=True)
        page = navegador.new_page(viewport={"width": 1500, "height": 950})
        try:
            _abrir_editor_3d(page)
            page.evaluate(
                """() => window.postMessage({
                    type: 'HOLTMONT_3D_IMPORT_ERROR',
                    reason: 'ningún nodo de la escena pasó la validación',
                }, '*')"""
            )
            page.wait_for_selector(".swal2-popup", timeout=10000)
            texto = page.locator(".swal2-popup").inner_text()
            assert "no pudo abrir el diseño" in texto.lower()
            assert "pasó la validación" in texto

            estado = page.evaluate(
                "() => document.querySelector('#app').__vue_app__._instance.proxy.design3DStatus")
            assert estado == "ERROR"
        finally:
            navegador.close()


def test_un_diseno_dibujado_a_medias_se_avisa_con_las_piezas_que_faltan():
    with sync_playwright() as p:
        navegador = p.chromium.launch(headless=True)
        page = navegador.new_page(viewport={"width": 1500, "height": 950})
        try:
            _abrir_editor_3d(page)
            page.evaluate(
                """() => window.postMessage({
                    type: 'HOLTMONT_3D_IMPORT_ACK',
                    nodeCount: 9,
                    dropped: [{ id: 'door_1', type: 'door', reason: 'position: Invalid input' }],
                }, '*')"""
            )
            page.wait_for_selector(".swal2-popup", timeout=10000)
            texto = page.locator(".swal2-popup").inner_text()
            assert "incompleto" in texto.lower()
            assert "door" in texto
        finally:
            navegador.close()


def test_un_acuse_limpio_no_interrumpe_a_nadie():
    """Sin descartes no hay nada que avisar: el aviso solo aparece si falta algo."""
    with sync_playwright() as p:
        navegador = p.chromium.launch(headless=True)
        page = navegador.new_page(viewport={"width": 1500, "height": 950})
        try:
            _abrir_editor_3d(page)
            page.evaluate(
                """() => window.postMessage({
                    type: 'HOLTMONT_3D_IMPORT_ACK', nodeCount: 10, dropped: [],
                }, '*')"""
            )
            page.wait_for_timeout(1000)
            assert page.locator(".swal2-popup").count() == 0
        finally:
            navegador.close()
