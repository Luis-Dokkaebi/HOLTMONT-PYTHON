"""
El Plano 2D y el Editor 3D, recorridos como los recorre una persona.

Las pruebas de `test_plano_2d.py` cubren la geometría, el dibujo y el contrato
estático. Aquí se comprueba lo único que aquellas no pueden: que al escribir la
descripción y pulsar el botón, el plano **aparece en la pantalla** con las
medidas que se pidieron, y que el editor 3D recibe la misma habitación.

Es la parte que fallaba en silencio: el modal abría, la imagen llegaba, y nadie
notaba que las medidas no eran las suyas.
"""

from __future__ import annotations

from playwright.sync_api import sync_playwright

BASE_URL = "http://localhost:8000"

# Cada caso: lo que se escribe, y las dos cotas que el plano tiene que mostrar.
CASOS_UI = [
    ("habitación de 8 x 5 m con una puerta", "8.00 m", "5.00 m", 1, 0),
    ("oficina de 6 x 4 m con una puerta y dos ventanas", "6.00 m", "4.00 m", 1, 2),
    ("bodega de 12 x 8 m con 2 puertas", "12.00 m", "8.00 m", 2, 0),
]


def _abrir_formulario(page):
    """Entra a la Pre Work Order sin pasar por credenciales reales."""
    page.goto(BASE_URL)
    page.wait_for_selector(".login-card", state="visible", timeout=15000)
    page.evaluate(
        "() => { const app = document.querySelector('#app').__vue_app__._instance.proxy;"
        " app.isLoggedIn = true; app.currentView = 'WORKORDER_FORM'; }")
    page.wait_for_selector("#campoConcepto", timeout=15000)


def _generar_plano(page, descripcion):
    page.fill("#campoConcepto", descripcion)
    page.click("button[title='Generar Plano 2D con IA']")
    page.wait_for_selector("svg[aria-label='Plano 2D a escala']", timeout=20000)


def test_el_plano_aparece_con_las_medidas_que_se_escribieron():
    """El recorrido completo, con los tres casos, en el navegador."""
    with sync_playwright() as p:
        navegador = p.chromium.launch(headless=True)
        page = navegador.new_page(viewport={"width": 1500, "height": 950})
        errores = []
        page.on("console", lambda m: errores.append(m.text) if m.type == "error" else None)
        try:
            _abrir_formulario(page)
            # El formulario ya emite errores propios al montar (un diagrama con
            # `d="M 15% 18% …"`, que no es `path` válido). No son de esta
            # función, así que la comparación es contra ese estado inicial: lo
            # que se vigila es no *añadir* errores nuevos.
            page.wait_for_timeout(800)
            basales = set(errores)

            for descripcion, cota_a, cota_b, puertas, ventanas in CASOS_UI:
                _generar_plano(page, descripcion)
                svg = page.locator("svg[aria-label='Plano 2D a escala']")
                contenido = svg.inner_html()

                assert cota_a in contenido, f"{descripcion}: falta la cota {cota_a}"
                assert cota_b in contenido, f"{descripcion}: falta la cota {cota_b}"
                assert contenido.count('class="muro"') == 4, descripcion
                assert contenido.count('class="puerta"') == puertas, descripcion
                assert contenido.count('class="ventana"') == ventanas, descripcion

                # El del pie del modal: hay otro "Cerrar" en la cabecera del
                # formulario, que queda detrás del overlay.
                page.click(".custom-modal-footer button:has-text('Cerrar')")
                page.wait_for_selector("svg[aria-label='Plano 2D a escala']",
                                       state="detached", timeout=5000)

            nuevos = [e for e in errores if e not in basales and "favicon" not in e]
            assert not nuevos, f"Generar el plano añadió errores de consola: {nuevos}"
        finally:
            navegador.close()


def test_el_plano_dice_que_salio_de_las_medidas_escritas():
    """
    La procedencia se ve en pantalla: no es lo mismo un plano con las medidas
    que escribió el usuario que uno deducido por el agente.
    """
    with sync_playwright() as p:
        navegador = p.chromium.launch(headless=True)
        page = navegador.new_page(viewport={"width": 1500, "height": 950})
        try:
            _abrir_formulario(page)
            _generar_plano(page, "habitación de 8 x 5 m con una puerta")

            assert "Dibujado con las medidas escritas" in page.content()
            assert "1 puerta(s)" in page.content()
        finally:
            navegador.close()


def test_sin_medidas_se_explica_en_vez_de_dibujar_cualquier_cosa():
    """
    El fallo que se venía a quitar: antes salía un plano igualmente, con medidas
    inventadas. Ahora el modal no llega a mostrar nada y se dice qué falta.
    """
    with sync_playwright() as p:
        navegador = p.chromium.launch(headless=True)
        page = navegador.new_page(viewport={"width": 1500, "height": 950})
        try:
            _abrir_formulario(page)
            page.fill("#campoConcepto", "pintar la fachada del edificio")
            page.click("button[title='Generar Plano 2D con IA']")

            page.wait_for_selector(".swal2-popup", timeout=20000)
            texto = page.locator(".swal2-popup").inner_text()
            assert "medidas" in texto.lower(), texto
            assert page.locator("svg[aria-label='Plano 2D a escala']").count() == 0
        finally:
            navegador.close()


def test_el_editor_3d_recibe_la_misma_habitacion_del_plano():
    """
    Las dos vistas cuentan lo mismo: tras generar el plano, el modelo que se le
    manda al editor 3D tiene los mismos cuatro muros y la misma puerta.
    """
    with sync_playwright() as p:
        navegador = p.chromium.launch(headless=True)
        page = navegador.new_page(viewport={"width": 1500, "height": 950})
        try:
            _abrir_formulario(page)
            _generar_plano(page, "habitación de 8 x 5 m con una puerta")

            escena = page.evaluate(
                "() => { const app = document.querySelector('#app').__vue_app__._instance.proxy;"
                " return app.saved3DProjectData; }")

            assert escena, "El editor 3D se quedó sin el modelo del plano"
            tipos = [n["type"] for n in escena["nodes"].values()]
            assert tipos.count("wall") == 4
            assert tipos.count("door") == 1

            largos = sorted(
                round(((n["end"][0] - n["start"][0]) ** 2
                       + (n["end"][1] - n["start"][1]) ** 2) ** 0.5, 2)
                for n in escena["nodes"].values() if n["type"] == "wall")
            assert largos == [5.0, 5.0, 8.0, 8.0], largos
        finally:
            navegador.close()


def test_el_boton_del_editor_3d_levanta_el_modelo_por_si_solo():
    """
    Sin haber pulsado antes ni el plano ni la Agencia Paperclip, el botón del
    editor 3D tiene que traer el modelo de la descripción. Antes abría el
    editor vacío y sin decir nada.
    """
    with sync_playwright() as p:
        navegador = p.chromium.launch(headless=True)
        page = navegador.new_page(viewport={"width": 1500, "height": 950})
        try:
            _abrir_formulario(page)
            page.fill("#campoConcepto", "taller de 10 x 6 m con dos puertas")
            page.click("button[title='Abrir Editor 3D']")

            page.wait_for_function(
                "() => { const app = document.querySelector('#app').__vue_app__._instance.proxy;"
                " return !!app.saved3DProjectData; }", timeout=20000)

            escena = page.evaluate(
                "() => document.querySelector('#app').__vue_app__._instance.proxy.saved3DProjectData")
            tipos = [n["type"] for n in escena["nodes"].values()]
            assert tipos.count("wall") == 4
            assert tipos.count("door") == 2
        finally:
            navegador.close()
