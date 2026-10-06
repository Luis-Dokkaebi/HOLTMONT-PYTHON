"""
La foto de la persona junto a su nombre, en la barra de su tracker.

Reporte del dueño (2026-10-06), con captura del tracker de Aviel Juarez
Olivares: «No veo la foto de esta persona en su tracker a lado de su nombre».

La foto ya llegaba al navegador —`/api/config` entrega `directory` con la
ficha de cada persona (`organigrama.enriquecer_directorio`)— pero solo la
pintaban las tarjetas del directorio. La barra del tracker mostraba el icono
de hoja y el nombre.

Lo que se fija aquí, en el navegador:

1. el tracker de alguien con ficha pinta su foto, servida por `/fotos/`, y la
   imagen carga de verdad (no basta con que exista la etiqueta);
2. quien no tiene foto ve su inicial, con la misma caja, como en el
   directorio;
3. una hoja de ventas no lleva foto ni inicial: no es el tracker de una
   persona, aunque `people` traiga una fila `ANTONIA_VENTAS`.
"""

from __future__ import annotations

import pytest
from playwright.sync_api import sync_playwright

BASE_URL = "http://localhost:8000"

ENCABEZADOS = ["FOLIO", "CONCEPTO", "AVANCE %", "STATUS"]

DIRECTORIO = [
    {"name": "AVIEL JUAREZ OLIVARES", "dept": "CONSTRUCCION", "type": "ESTANDAR",
     "nombre": "Aviel Juarez Olivares", "puesto": "Residente de obra",
     "foto": "/fotos/aviel-juarez-olivares.jpg"},
    {"name": "DANIELA CASTRO", "dept": "GENERAL", "type": "ESTANDAR",
     "nombre": "Daniela Castro", "puesto": "", "foto": ""},
    # `people` en producción trae esta fila aunque no sea una persona.
    {"name": "ANTONIA_VENTAS", "dept": "VENTAS", "type": "VENTAS",
     "nombre": "ANTONIA_VENTAS", "puesto": "", "foto": ""},
]

MONTAR_TRACKER = """(datos) => {
    const app = document.querySelector('#app').__vue_app__._instance.proxy;
    app.config = Object.assign({}, app.config, {directory: datos.directorio});
    app.isLoggedIn = true;
    app.currentUsername = datos.usuario;
    app.currentUser = datos.hoja;
    app.currentView = 'STAFF_TRACKER';
    app.trackerSubView = 'TASKS';
    app.staffTracker.name = datos.hoja;
    app.staffTracker.isLoading = false;
    app.staffTracker.headers = datos.encabezados;
    app.staffTracker.data = [];
    app.staffTracker.history = [];
}"""

FOTO_DE_LA_BARRA = """() => {
    const barra = document.querySelector('.barra-tracker');
    if (!barra) return null;
    const img = barra.querySelector('img.foto-tracker');
    const inicial = barra.querySelector('.foto-tracker.staff-foto-inicial');
    return {
        src: img ? img.getAttribute('src') : null,
        cargada: img ? (img.complete && img.naturalWidth > 0) : false,
        inicial: inicial ? inicial.textContent.trim() : null,
        texto: barra.textContent,
    };
}"""


def _abrir(page, usuario: str, hoja: str) -> dict:
    page.goto(BASE_URL)
    page.wait_for_function("() => document.querySelector('#app').__vue_app__")
    page.evaluate(MONTAR_TRACKER, {
        "usuario": usuario, "hoja": hoja,
        "encabezados": ENCABEZADOS, "directorio": DIRECTORIO,
    })
    page.wait_for_selector(".barra-tracker")
    page.wait_for_function(
        "() => { const i = document.querySelector('.barra-tracker img.foto-tracker');"
        " return !i || i.complete; }"
    )
    return page.evaluate(FOTO_DE_LA_BARRA)


def test_el_tracker_pinta_la_foto_de_su_dueno(live_server):
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        page = browser.new_page()
        barra = _abrir(page, "AVIEL_JUAREZ", "AVIEL JUAREZ OLIVARES")
        browser.close()

    assert barra is not None, "no se montó la barra del tracker"
    assert barra["src"] == "/fotos/aviel-juarez-olivares.jpg"
    assert barra["cargada"], "la etiqueta existe pero la foto no cargó"
    assert "AVIEL JUAREZ OLIVARES" in barra["texto"]


def test_sin_foto_se_ve_la_inicial(live_server):
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        page = browser.new_page()
        barra = _abrir(page, "DANIELA_CASTRO", "DANIELA CASTRO")
        browser.close()

    assert barra["src"] is None
    assert barra["inicial"] == "D"
    assert "DANIELA CASTRO" in barra["texto"]


@pytest.mark.parametrize("usuario,hoja", [
    ("ANTONIA_VENTAS", "ANTONIA_VENTAS"),   # Antonia en su propia vista
    ("LUIS_CARLOS", "ANTONIA_VENTAS"),      # otra cuenta abre el core de ventas
    ("ALFONSO_CORREA", "ALFONSO CORREA (VENTAS)"),
])
def test_una_hoja_de_ventas_no_lleva_foto(live_server, usuario, hoja):
    """Una hoja de ventas no es el tracker de una persona: ni foto ni inicial."""
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        page = browser.new_page()
        barra = _abrir(page, usuario, hoja)
        browser.close()

    assert barra["src"] is None
    assert barra["inicial"] is None
    assert hoja in barra["texto"]
