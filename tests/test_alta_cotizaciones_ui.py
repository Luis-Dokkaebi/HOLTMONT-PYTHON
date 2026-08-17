"""
El aviso "Campos obligatorios" en la pantalla real, visto por el navegador.

El defecto reportado (2026-08-17): al dar de alta en **Cotizaciones** salía
"Falta PRIORIDAD, RIESGOS, FEC. EST. FIN" y no se podía guardar nada. Esa
pantalla no captura ninguno de los tres: es una tabla de cotizaciones, con
`Prio. cot.`, `F. Visita`, `F. Inicio` y `F. Entrega`.

El primer arreglo miró las columnas de la tabla, y no bastó: la tabla de
cotizaciones no tiene cabecera fija —rinde las columnas que traiga `quotes` en
la base—, así que basta con que una se llame como uno de los tres campos para
que el aviso vuelva. Por eso aquí las tablas de ventas llevan además las tres
columnas puestas a mano: si el candado se decidiera por la cabecera, estas
pruebas volverían a fallar como falló producción.

`tests/test_campos_obligatorios_actividad.py` comprueba el validador leyendo el
fuente; eso no distingue entre la regla escrita y el diálogo que ve el usuario.
Aquí se monta la tabla, se asigna vendedor y se pulsa Guardar, que es
exactamente lo que hizo quien reportó el defecto.
"""

from __future__ import annotations

import os
import pathlib

from playwright.sync_api import sync_playwright

BASE_URL = "http://localhost:8000"

CAPTURAS = pathlib.Path(__file__).resolve().parent.parent / "verification" / "screenshots"

# Las columnas de la tabla de cotizaciones tal como las rinde la API
# (`QUOTE_HEADER_MAP` de api/services/sheets.py), más las tres del Tracker: en
# la base pueden aparecer con cualquier nombre y el candado no debe reaccionar.
ENCABEZADOS_COTIZACIONES = [
    "FOLIO", "AREA", "CLIENTE", "CONCEPTO", "CLASIFICACION", "VENDEDOR",
    "F. VISITA", "F. INICIO", "F. ENTREGA", "DIAS", "AVANCE", "ESTATUS",
    "COMENTARIOS", "REQUISITOR", "PRIO. COT.", "INFO CLIENTE", "F2",
    "COTIZACION", "TIMELINE", "LAYOUT",
    "PRIORIDAD", "RIESGOS", "FEC. EST. FIN",
]
ENCABEZADOS_TRACKER = ["FOLIO", "CONCEPTO", "AVANCE", "FECHA_ESTIMADA_FIN", "RELOJ",
                       "PRIORIDADES", "RIESGOS", "ESTATUS"]


def _cotizacion(temp_id: str, cliente: str, concepto: str, vendedor: str = "") -> dict:
    """Una cotización recién dada de alta: sin folio y con los tres campos vacíos."""
    fila = {clave: "" for clave in ENCABEZADOS_COTIZACIONES}
    fila.update({"_isNew": True, "_tempId": temp_id, "AREA": "VENTAS",
                 "CLIENTE": cliente, "CONCEPTO": concepto, "CLASIFICACION": "A",
                 "VENDEDOR": vendedor, "DIAS": 0, "AVANCE": "0"})
    return fila


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
    app.staffTracker.data = datos.filas;
    app.staffTracker.history = [];
}"""

# Asignar es lo que hace la vendedora al dar de alta: elegir a quién le toca.
# Se usa el mismo selector que abre la celda de VENDEDOR en la tabla.
ASIGNAR_VENDEDOR = """([indice, vendedor]) => {
    const app = document.querySelector('#app').__vue_app__._instance.proxy;
    app.staffTracker.data[indice].VENDEDOR = vendedor;
}"""

GUARDAR_FILA = """(indice) => {
    const app = document.querySelector('#app').__vue_app__._instance.proxy;
    app.saveRow(app.staffTracker.data[indice]);
}"""

GUARDAR_TODO = """() => {
    const app = document.querySelector('#app').__vue_app__._instance.proxy;
    app.saveAllTrackerRows();
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

FOLIOS = """() => {
    const app = document.querySelector('#app').__vue_app__._instance.proxy;
    return app.staffTracker.data.map(f => String(f.FOLIO || f.ID || ''));
}"""


def _pantalla_montada(page, hoja: str, usuario: str, encabezados: list, filas: list):
    page.goto(BASE_URL)
    page.wait_for_selector("#app", state="attached", timeout=15000)
    page.wait_for_function(
        "() => document.querySelector('#app') && document.querySelector('#app').__vue_app__",
        timeout=15000)
    page.evaluate(MONTAR, {"hoja": hoja, "usuario": usuario,
                           "encabezados": encabezados, "filas": filas})
    page.wait_for_selector(".table-excel tbody tr", timeout=10000)


def _capturar(page, nombre: str) -> None:
    """Deja la evidencia del ticket en verification/screenshots."""
    os.makedirs(CAPTURAS, exist_ok=True)
    page.screenshot(path=str(CAPTURAS / nombre), full_page=False)


def test_antonia_da_de_alta_una_cotizacion_asignada_y_se_guarda():
    """El defecto reportado: aquí no se puede abrir ningún aviso de esos tres."""
    with sync_playwright() as p:
        navegador = p.chromium.launch(headless=True)
        page = navegador.new_page(viewport={"width": 1400, "height": 800})
        try:
            _pantalla_montada(
                page, "ANTONIA_VENTAS", "ANTONIA_VENTAS", ENCABEZADOS_COTIZACIONES,
                [_cotizacion("tmp-cot-ui", "NEMAK", "COTIZAR NAVE INDUSTRIAL")])
            page.evaluate(ASIGNAR_VENDEDOR, [0, "RAMIRO RODRIGUEZ"])
            page.evaluate(GUARDAR_FILA, 0)
            page.wait_for_timeout(2000)
            dialogo = page.evaluate(DIALOGO)
            folios = page.evaluate(FOLIOS)
            _capturar(page, "cotizaciones_alta_sin_campos_obligatorios.png")

            assert dialogo is None or "Campos obligatorios" not in dialogo["titulo"], (
                f"Cotizaciones sigue pidiendo los tres campos: {dialogo}")
            assert folios[0], "la cotización no recibió folio: no llegó a guardarse"
        finally:
            navegador.close()


def test_antonia_guarda_todo_con_varias_cotizaciones_asignadas():
    """
    "Guardar Todo" es la otra puerta de la tabla y valida el lote entero: una
    sola fila juzgada de más bloqueaba toda la captura del día.
    """
    with sync_playwright() as p:
        navegador = p.chromium.launch(headless=True)
        page = navegador.new_page(viewport={"width": 1400, "height": 800})
        try:
            _pantalla_montada(
                page, "ANTONIA_VENTAS", "ANTONIA_VENTAS", ENCABEZADOS_COTIZACIONES,
                [_cotizacion("tmp-lote-1", "NEMAK", "COTIZAR NAVE INDUSTRIAL"),
                 _cotizacion("tmp-lote-2", "KIA", "COTIZAR RACKS DE ALMACEN")])
            page.evaluate(ASIGNAR_VENDEDOR, [0, "RAMIRO RODRIGUEZ"])
            page.evaluate(ASIGNAR_VENDEDOR, [1, "TERESA GARZA"])
            page.evaluate(GUARDAR_TODO)
            # "Guardar Todo" pregunta antes de escribir; el aviso de campos
            # obligatorios saldría en lugar de esa confirmación.
            page.wait_for_selector(".swal2-popup", timeout=10000)
            page.wait_for_timeout(800)
            dialogo = page.evaluate(DIALOGO)
            _capturar(page, "cotizaciones_guardar_todo_sin_candado.png")

            assert dialogo is not None, "no salió ningún diálogo"
            assert "Campos obligatorios" not in dialogo["titulo"], dialogo
            assert "Guardar" in dialogo["titulo"], dialogo
        finally:
            navegador.close()


def test_el_tracker_sigue_pidiendo_los_tres_campos():
    """El candado no se levantó: en el Tracker se siguen exigiendo."""
    with sync_playwright() as p:
        navegador = p.chromium.launch(headless=True)
        page = navegador.new_page(viewport={"width": 1400, "height": 800})
        try:
            _pantalla_montada(page, "JAIME OLIVO", "JAIME_OLIVO",
                              ENCABEZADOS_TRACKER, [dict(ACTIVIDAD_NUEVA)])
            page.evaluate(GUARDAR_FILA, 0)
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
