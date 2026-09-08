"""
El Plano 3D de punta a punta, con el editor de verdad al otro lado del iframe.

`tests/test_arquitectura_pascal_contrato.py` comprueba la escena que se genera;
`tests/test_editor_3d_puente_ui.py`, el intercambio de mensajes. Falta la
pregunta que hizo el dueño: **¿se ve?** Ni el contrato ni los mensajes lo
responden: el bug del lienzo negro pasaba las dos cosas —el editor recibía la
escena y contestaba— y no dibujaba nada, porque el fallo ocurría después, en el
bucle de render.

Aquí se escribe la descripción, se pulsa el botón, y se cuenta la geometría que
quedó dibujada dentro del iframe (`window.__holtmontProbe()` del puente).

Necesita el editor servido en `EDITOR_URL`. Como es otro repositorio, la prueba
se SALTA -- con motivo visible -- cuando no está levantado, en vez de dar por
bueno lo que no se comprobó:

    cd ../holtmont-3d-editor && bun run build && bunx next start -p 3002 --dir apps/editor
"""

from __future__ import annotations

import os
import re
import socket
import urllib.error
import urllib.request

import pytest
from playwright.sync_api import sync_playwright

BASE_URL = "http://localhost:8000"
EDITOR_URL = os.environ.get("HOLTMONT_EDITOR_URL", "http://localhost:3002")

# Con `HOLTMONT_E2E_CAPTURAS=<directorio>` cada caso deja su captura. Sirve para
# enseñar el resultado sin volver a montar todo el tinglado.
DIR_CAPTURAS = os.environ.get("HOLTMONT_E2E_CAPTURAS")

# Lo que cada descripción tiene que llegar a DIBUJAR. Contar nodos no basta:
# el bug tenía todos los nodos en el store y cero geometría en pantalla.
CASOS = [
    ("Cuarto de 5 x 4 m con una puerta", {"wall": 4, "door": 1, "slab": 1}),
    ("Bodega de 12 x 8 m con dos puertas y cuatro ventanas",
     {"wall": 4, "door": 2, "window": 4, "slab": 1}),
    ("Oficina de 6 x 4 m con una puerta y dos ventanas",
     {"wall": 4, "door": 1, "window": 2, "slab": 1}),
]


def _editor_servido() -> bool:
    try:
        with urllib.request.urlopen(EDITOR_URL, timeout=5) as respuesta:
            return respuesta.status == 200
    except (urllib.error.URLError, socket.timeout, OSError):
        return False


pytestmark = pytest.mark.skipif(
    not _editor_servido(),
    reason=f"El editor 3D no responde en {EDITOR_URL}: ver el docstring de este archivo",
)


def _abrir_prework(page):
    page.goto(BASE_URL)
    page.wait_for_selector(".login-card", state="visible", timeout=15000)
    page.evaluate(
        """(urlEditor) => {
            const app = document.querySelector('#app').__vue_app__._instance.proxy;
            app.isLoggedIn = true;
            app.pascalEditorUrl = urlEditor;   // el editor local, no el de Vercel
            app.currentView = 'WORKORDER_FORM';
        }""",
        EDITOR_URL,
    )
    page.wait_for_selector("#campoConcepto", timeout=15000)


def _marco_del_editor(page):
    """El frame del iframe, cuando termine de engancharse."""
    page.wait_for_function(
        """(url) => Array.from(document.querySelectorAll('iframe'))
              .some((f) => f.contentWindow && f.src.startsWith(url))""",
        arg=EDITOR_URL, timeout=60000)
    for _ in range(120):
        for marco in page.frames:
            if marco.url.startswith(EDITOR_URL):
                return marco
        page.wait_for_timeout(500)
    raise AssertionError(f"El iframe del editor ({EDITOR_URL}) nunca se enganchó")


def _geometria_dibujada(page):
    """Lo que el motor 3D acabó dibujando dentro del iframe."""
    marco = _marco_del_editor(page)
    marco.wait_for_function(
        "() => { const s = window.__holtmontProbe && window.__holtmontProbe();"
        " return s && (s.porTipo.wall ? s.porTipo.wall.conGeometria : 0) > 0; }",
        timeout=90000)
    return marco.evaluate("() => window.__holtmontProbe()")


@pytest.mark.parametrize("descripcion,esperado", CASOS)
def test_lo_que_se_pide_es_lo_que_se_dibuja(descripcion, esperado):
    with sync_playwright() as p:
        navegador = p.chromium.launch(
            headless=True,
            args=["--use-gl=angle", "--use-angle=swiftshader", "--enable-unsafe-swiftshader"])
        page = navegador.new_page(viewport={"width": 1400, "height": 900})
        excepciones = []
        page.on("pageerror", lambda e: excepciones.append(str(e)))
        try:
            _abrir_prework(page)
            page.fill("#campoConcepto", descripcion)
            page.click("button[title='Abrir Editor 3D']")

            page.wait_for_selector("#pascal-editor-iframe", timeout=30000)
            sonda = _geometria_dibujada(page)

            for tipo, minimo in esperado.items():
                dibujados = sonda["porTipo"].get(tipo, {}).get("conGeometria", 0)
                assert dibujados >= minimo, (
                    f"{descripcion}: se dibujaron {dibujados} '{tipo}', se esperaban {minimo}"
                    f" (sonda: {sonda['porTipo']})")

            if DIR_CAPTURAS:
                os.makedirs(DIR_CAPTURAS, exist_ok=True)
                nombre = re.sub(r"[^a-z0-9]+", "-", descripcion.lower()).strip("-")[:60]
                page.screenshot(path=os.path.join(DIR_CAPTURAS, f"{nombre}.png"))

            # Una escena que no mide nada es una escena que no se ve.
            assert sonda["mayorLado"] > 1, f"{descripcion}: la escena mide {sonda['mayorLado']} m"

            # Una excepción dentro de un `useFrame` mata el bucle de render sin
            # avisar: ese era el síntoma exacto del lienzo negro.
            assert not excepciones, f"{descripcion}: excepciones en el navegador: {excepciones}"
        finally:
            navegador.close()


def test_el_editor_confirma_lo_que_recibio():
    """El acuse tiene que llegar, y sin piezas descartadas."""
    with sync_playwright() as p:
        navegador = p.chromium.launch(
            headless=True,
            args=["--use-gl=angle", "--use-angle=swiftshader", "--enable-unsafe-swiftshader"])
        page = navegador.new_page(viewport={"width": 1400, "height": 900})
        try:
            page.add_init_script(
                """window.addEventListener('message', (e) => {
                    if (e.data && e.data.type === 'HOLTMONT_3D_IMPORT_ACK') {
                        window.__acuse = e.data;
                    }
                });""")
            _abrir_prework(page)
            page.fill("#campoConcepto", "Cuarto de 5 x 4 m con una puerta")
            page.click("button[title='Abrir Editor 3D']")
            page.wait_for_function("() => window.__acuse", timeout=90000)

            acuse = page.evaluate("() => window.__acuse")
            assert acuse["nodeCount"] > 0
            assert acuse["dropped"] == [], f"El editor no supo dibujar: {acuse['dropped']}"
        finally:
            navegador.close()
