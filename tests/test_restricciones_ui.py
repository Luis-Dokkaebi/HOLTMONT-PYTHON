"""
«Restricciones y Comentarios», recorrida como la recorre Toñita.

`test_restricciones_editable.py` comprueba la regla de permiso aislada. Aquí se
comprueba lo único que aquella no puede: que con la actividad **ya asignada** la
celda de la tabla se deja escribir en la pantalla, y que al pulsar guardar el
texto sale hacia el backend y el backend lo acepta.

Es el recorrido que fallaba: la fila se daba de alta, el backend le ponía folio,
y a partir de ese momento la celda quedaba de solo lectura. Nada avisaba —el
`textarea` seguía ahí, con su borde y su cursor— así que el defecto solo se veía
al intentar teclear.

La tabla se puebla inyectando el estado del componente en vez de leer la hoja:
los encabezados que se inyectan son los que rinde `sheets.TASK_HEADER_MAP`, y se
comprueba contra ese mapa para que la prueba no se quede con una copia que se
desactualice.
"""

from __future__ import annotations

import json

import pytest
from playwright.sync_api import sync_playwright

BASE_URL = "http://localhost:8000"

# Lo que anota Toñita cuando la actividad ya está repartida. Con acento a
# propósito: la celda es texto libre en español.
TEXTO = "FALTA PLANO DEL CLIENTE — revisar con Terán"

# Una fila viva del tracker de ventas: ya tiene folio, así que está dada de alta.
FILA = {
    "FOLIO": "AV-1001", "ID": "AV-1001", "ALTA": "VENTAS", "FECHA": "11/08/26",
    "CONCEPTO": "COTIZAR NAVE INDUSTRIAL", "INVOLUCRADOS": "AP",
    "AVANCE %": "70", "FECHA_ESTIMADA_FIN": "2026-08-17", "RELOJ": "3",
    "RESTRICCIONES": "", "PRIORIDADES": "NORMAL", "RIESGOS": "BAJO",
    "STATUS": "ASIGNADA", "_rowIndex": 2,
}

INYECTAR_TRACKER = """(payload) => {
    const app = document.querySelector('#app').__vue_app__._instance.proxy;
    app.isLoggedIn = true;
    app.currentUser = 'ANTONIA_VENTAS';
    app.currentUsername = 'ANTONIA_VENTAS';
    app.currentRole = 'TONITA';
    app.currentStaffName = 'ANTONIA_VENTAS';
    app.currentView = 'STAFF_TRACKER';
    app.trackerSubView = 'TASKS';
    app.staffTracker.name = 'ANTONIA_VENTAS';
    app.staffTracker.isLoading = false;
    app.staffTracker.headers = payload.headers;
    app.staffTracker.history = [];
    app.staffTracker.data = payload.rows;
}"""


def _encabezados_de_la_api() -> list[str]:
    """Los que el frontend recibe de verdad, tomados del mapa del backend."""
    from api.services.sheets import TASK_HEADER_MAP

    return [h for h, _ in TASK_HEADER_MAP]


def _abrir_tracker(page) -> None:
    page.goto(BASE_URL)
    page.wait_for_selector(".login-card", state="visible", timeout=20000)
    page.evaluate(INYECTAR_TRACKER,
                  {"headers": _encabezados_de_la_api(), "rows": [dict(FILA)]})
    page.wait_for_selector("table.table-excel tbody tr", timeout=15000)


def _celda_de_restricciones(page):
    """El `textarea` de la columna, localizado por el rótulo de su encabezado."""
    rotulos = page.locator("table.table-excel thead th").all_inner_texts()
    indice = next((i for i, t in enumerate(rotulos)
                   if "Restricciones" in t), None)
    assert indice is not None, f"la columna no está en la tabla: {rotulos}"

    # `nth-child` es 1-indexado y la primera celda de cada fila es el número.
    celda = page.locator(f"table.table-excel tbody tr:first-child "
                         f"td:nth-child({indice + 1})")
    return celda.locator("textarea")


@pytest.fixture()
def pagina():
    with sync_playwright() as p:
        navegador = p.chromium.launch(headless=True)
        page = navegador.new_page(viewport={"width": 1500, "height": 900})
        try:
            yield page
        finally:
            navegador.close()


def test_la_celda_se_deja_escribir_con_la_actividad_ya_asignada(pagina) -> None:
    """El defecto reportado, visto desde la pantalla."""
    _abrir_tracker(pagina)
    celda = _celda_de_restricciones(pagina)

    assert celda.count() == 1, "la celda no se rinde como campo de texto"
    assert not celda.evaluate("el => el.readOnly"), (
        "la celda de «Restricciones y Comentarios» está en solo lectura con la "
        "actividad ya asignada: no se puede anotar la restricción"
    )

    celda.fill(TEXTO)
    assert celda.input_value() == TEXTO


def test_al_guardar_el_texto_llega_al_backend_y_se_acepta(pagina) -> None:
    """
    Escribir sin guardar no resuelve nada.

    Se vigila la petición real que dispara el botón de guardar de la fila
    (`saveRow` -> `/api/legacy/updateTask`) y la respuesta del servidor.
    """
    _abrir_tracker(pagina)
    celda = _celda_de_restricciones(pagina)
    celda.fill(TEXTO)

    with pagina.expect_response(
        lambda r: "/api/legacy/updateTask" in r.url, timeout=20000
    ) as espera:
        pagina.click("table.table-excel tbody tr:first-child td:last-child button")
    respuesta = espera.value

    enviado = json.loads(respuesta.request.post_data)
    assert enviado["task"].get("RESTRICCIONES") == TEXTO, (
        "el texto no viajó en el guardado; se envió: "
        f"{enviado['task'].get('RESTRICCIONES')!r}"
    )

    devuelto = respuesta.json()
    assert devuelto.get("success") is True, devuelto
    assert devuelto["data"].get("RESTRICCIONES") == TEXTO, (
        f"el backend no conservó el texto: {devuelto['data'].get('RESTRICCIONES')!r}"
    )
