"""
El aviso "Campos obligatorios" en la pantalla real, vista por el navegador.

El defecto reportado (2026-08-17): al dar de alta en **Cotizaciones** salía
"Falta PRIORIDAD, RIESGOS, FEC. EST. FIN" y no se podía guardar nada. Esa tabla
no tiene ninguna de las tres columnas —lleva `Prio. cot.`, `F. Visita`,
`F. Inicio` y `F. Entrega`—, así que el aviso pedía tres datos que la pantalla
no tiene dónde capturar.

`tests/test_campos_obligatorios_actividad.py` comprueba el validador leyendo el
fuente; eso no distingue entre la regla escrita y el diálogo que el usuario ve.
Aquí se monta la tabla con las columnas de cada pantalla, se pulsa Guardar y se
mira si SweetAlert se abre, que es exactamente lo que reportó el dueño.

Las dos pruebas son la misma comprobación con la cabecera cambiada, porque el
arreglo es justo ese: el candado se decide por las columnas de la tabla abierta.
"""

from __future__ import annotations

import os
import pathlib

from playwright.sync_api import sync_playwright

BASE_URL = "http://localhost:8000"

CAPTURAS = pathlib.Path(__file__).resolve().parent.parent / "verification" / "screenshots"

# Las columnas de cada pantalla, tal como las rinde la API.
ENCABEZADOS_COTIZACIONES = ["FOLIO", "AREA", "CLIENTE", "CONCEPTO", "CLASIFICACION",
                            "VENDEDOR", "F. VISITA", "F. INICIO", "F. ENTREGA", "DIAS",
                            "AVANCE", "ESTATUS", "COMENTARIOS", "PRIO. COT."]
ENCABEZADOS_TRACKER = ["FOLIO", "CONCEPTO", "AVANCE", "FECHA_ESTIMADA_FIN", "RELOJ",
                       "PRIORIDADES", "RIESGOS", "ESTATUS"]

COTIZACION_NUEVA = {
    "_isNew": True, "_tempId": "tmp-cot-ui", "FOLIO": "", "AREA": "VENTAS",
    "CLIENTE": "NEMAK", "CONCEPTO": "COTIZAR NAVE INDUSTRIAL", "CLASIFICACION": "A",
    "VENDEDOR": "ANTONIA VENTAS", "F. VISITA": "", "F. INICIO": "", "F. ENTREGA": "",
    "DIAS": 0, "AVANCE": "0", "ESTATUS": "", "COMENTARIOS": "", "PRIO. COT.": "",
}

ACTIVIDAD_NUEVA = {
    "_isNew": True, "_tempId": "tmp-trk-ui", "FOLIO": "", "CONCEPTO": "REVISAR PLANOS",
    "AVANCE": "0", "FECHA_ESTIMADA_FIN": "", "RELOJ": 0, "PRIORIDADES": "",
    "RIESGOS": "", "ESTATUS": "",
}

MONTAR = """(datos) => {
    const app = document.querySelector('#app').__vue_app__._instance.proxy;
    app.isLoggedIn = true;
    app.currentUsername = datos.usuario;
    app.currentUser = datos.hoja;
    app.currentView = 'STAFF_TRACKER';
    app.trackerSubView = 'TASKS';
    app.staffTracker.name = datos.hoja;
    app.staffTracker.isLoading = false;
    app.staffTracker.headers = datos.encabezados;
    app.staffTracker.data = [datos.fila];
    app.staffTracker.history = [];
}"""

GUARDAR_PRIMERA_FILA = """() => {
    const app = document.querySelector('#app').__vue_app__._instance.proxy;
    app.saveRow(app.staffTracker.data[0]);
}"""

# El diálogo que ve el usuario, o null si no se abrió ninguno.
DIALOGO = """() => {
    const caja = document.querySelector('.swal2-popup');
    if (!caja || caja.offsetParent === null) return null;
    const titulo = caja.querySelector('.swal2-title');
    const texto = caja.querySelector('.swal2-html-container');
    return { titulo: titulo ? titulo.textContent.trim() : '',
             texto: texto ? texto.textContent.trim() : '' };
}"""


def _pantalla_montada(page, hoja: str, usuario: str, encabezados: list, fila: dict):
    page.goto(BASE_URL)
    page.wait_for_selector("#app", state="attached", timeout=15000)
    page.wait_for_function(
        "() => document.querySelector('#app') && document.querySelector('#app').__vue_app__",
        timeout=15000)
    page.evaluate(MONTAR, {"hoja": hoja, "usuario": usuario,
                           "encabezados": encabezados, "fila": fila})
    page.wait_for_selector(".table-excel tbody tr", timeout=10000)


def _capturar(page, nombre: str) -> None:
    """Deja la evidencia del ticket en verification/screenshots."""
    os.makedirs(CAPTURAS, exist_ok=True)
    page.screenshot(path=str(CAPTURAS / nombre), full_page=False)


def test_cotizaciones_guarda_sin_pedir_prioridad_ni_riesgos():
    """El defecto reportado: aquí no se puede abrir ningún aviso de esos tres."""
    with sync_playwright() as p:
        navegador = p.chromium.launch(headless=True)
        page = navegador.new_page(viewport={"width": 1400, "height": 800})
        try:
            _pantalla_montada(page, "ANTONIA_VENTAS", "ANTONIA_VENTAS",
                              ENCABEZADOS_COTIZACIONES, dict(COTIZACION_NUEVA))
            page.evaluate(GUARDAR_PRIMERA_FILA)
            page.wait_for_timeout(1500)
            dialogo = page.evaluate(DIALOGO)
            _capturar(page, "cotizaciones_alta_sin_campos_obligatorios.png")

            assert dialogo is None or "Campos obligatorios" not in dialogo["titulo"], (
                f"Cotizaciones sigue exigiendo columnas que no tiene: {dialogo}")
        finally:
            navegador.close()


def test_el_tracker_sigue_pidiendo_los_tres_campos():
    """El candado no se levantó: donde las columnas existen, se siguen exigiendo."""
    with sync_playwright() as p:
        navegador = p.chromium.launch(headless=True)
        page = navegador.new_page(viewport={"width": 1400, "height": 800})
        try:
            _pantalla_montada(page, "JAIME OLIVO", "JAIME_OLIVO",
                              ENCABEZADOS_TRACKER, dict(ACTIVIDAD_NUEVA))
            page.evaluate(GUARDAR_PRIMERA_FILA)
            page.wait_for_selector(".swal2-popup", timeout=10000)
            # El diálogo entra con animación: sin la espera la captura sale con
            # la tabla ya oscurecida pero el recuadro todavía en blanco.
            page.wait_for_timeout(800)
            dialogo = page.evaluate(DIALOGO)
            _capturar(page, "tracker_alta_pide_campos_obligatorios.png")

            assert dialogo and "Campos obligatorios" in dialogo["titulo"], dialogo
            for campo in ("PRIORIDAD", "RIESGOS", "FEC. EST. FIN"):
                assert campo in dialogo["texto"], (campo, dialogo)
        finally:
            navegador.close()
