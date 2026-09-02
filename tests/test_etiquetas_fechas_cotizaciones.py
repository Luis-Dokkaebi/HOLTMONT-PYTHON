"""
Las columnas de fecha de Cotizaciones se rotulan con la palabra completa.

Lo reportado (BUG-0017, ANTONIA_VENTAS, 2026-08-26): en la tabla de
cotizaciones las tres columnas de fecha salían abreviadas —`F. visita`,
`F. inicio`, `F. entrega`— y el cliente pidió leerlas completas: `Fecha
Visita`, `Fecha Inicio`, `Fecha Entrega`.

El cambio es **solo de vista**. La columna sigue llamándose `F. VISITA` en la
hoja y en la base (`QUOTE_HEADER_MAP` de api/services/sheets.py), que es de
donde se leen y escriben los valores; por eso aquí se comprueban las dos cosas
a la vez: que el encabezado que ve el usuario está completo y que la fila
conserva sus claves originales.

Se prueba contra la pantalla real porque el rótulo tiene dos maneras de llegar
roto que un `assert` sobre el texto del archivo no ve: que la etiqueta no se
aplique (la tabla rinde el nombre crudo de la columna) y que se aplique pero no
quepa —la celda lleva `overflow:hidden` con `text-overflow:ellipsis`, así que
un ancho corto la dejaría en `Fecha Vi…`, tan abreviada como antes—.
"""

from __future__ import annotations

import os
import pathlib

from playwright.sync_api import sync_playwright

BASE_URL = "http://localhost:8000"

CAPTURAS = pathlib.Path(__file__).resolve().parent.parent / "verification" / "screenshots"

# Las columnas de la tabla de cotizaciones tal como las rinde la API
# (`QUOTE_HEADER_MAP` de api/services/sheets.py).
ENCABEZADOS_COTIZACIONES = [
    "FOLIO", "AREA", "CLIENTE", "CONCEPTO", "CLASIFICACION", "VENDEDOR",
    "F. VISITA", "F. INICIO", "F. ENTREGA", "DIAS", "AVANCE", "ESTATUS",
    "COMENTARIOS", "REQUISITOR", "PRIO. COT.", "INFO CLIENTE", "F2",
    "COTIZACION", "TIMELINE", "LAYOUT",
]

COTIZACION = {
    "FOLIO": "AV-0060", "AREA": "VENTAS", "CLIENTE": "NEMAK",
    "CONCEPTO": "COTIZAR NAVE INDUSTRIAL", "CLASIFICACION": "A",
    "VENDEDOR": "RAMIRO RODRIGUEZ", "F. VISITA": "01/03/26",
    "F. INICIO": "03/03/26", "F. ENTREGA": "10/03/26", "DIAS": 2,
    "AVANCE": "0", "ESTATUS": "PENDIENTE", "COMENTARIOS": "",
    "REQUISITOR": "", "PRIO. COT.": "ALTA", "INFO CLIENTE": "",
    "F2": "", "COTIZACION": "", "TIMELINE": "", "LAYOUT": "",
}

ETIQUETAS_ESPERADAS = {
    "F. VISITA": "Fecha Visita",
    "F. INICIO": "Fecha Inicio",
    "F. ENTREGA": "Fecha Entrega",
}

MONTAR = """(datos) => {
    const app = document.querySelector('#app').__vue_app__._instance.proxy;
    app.isLoggedIn = true;
    app.currentUsername = datos.usuario;
    app.currentUser = datos.hoja;
    app.currentView = 'STAFF_TRACKER';
    app.trackerSubView = datos.subVista;
    app.staffTracker.name = datos.hoja;
    app.staffTracker.isLoading = false;
    app.staffTracker.headers = datos.encabezados;
    app.staffTracker.data = datos.filas;
    app.staffTracker.history = datos.subVista === 'HISTORY' ? datos.filas : [];
}"""

# Cada encabezado con lo que se ve y lo que mide: `scrollWidth` mayor que
# `clientWidth` es exactamente el texto que la celda recorta con puntos
# suspensivos.
ENCABEZADOS_EN_PANTALLA = """() => {
    const filas = document.querySelectorAll('.table-excel thead tr');
    const fila = filas[filas.length - 1];
    return Array.from(fila.querySelectorAll('th')).map(th => {
        const caja = th.querySelector('div') || th;
        return { texto: th.innerText.trim(),
                 recortado: caja.scrollWidth > caja.clientWidth };
    });
}"""

CLAVES_DE_LA_FILA = """() => {
    const app = document.querySelector('#app').__vue_app__._instance.proxy;
    return Object.keys(app.staffTracker.data[0]);
}"""


def _pantalla_montada(page, sub_vista: str = "TASKS") -> None:
    page.goto(BASE_URL)
    page.wait_for_selector("#app", state="attached", timeout=15000)
    page.wait_for_function(
        "() => document.querySelector('#app') && document.querySelector('#app').__vue_app__",
        timeout=15000)
    page.evaluate(MONTAR, {"hoja": "ANTONIA_VENTAS", "usuario": "ANTONIA_VENTAS",
                           "subVista": sub_vista,
                           "encabezados": ENCABEZADOS_COTIZACIONES,
                           "filas": [dict(COTIZACION)]})
    page.wait_for_selector(".table-excel thead th", timeout=10000)


def _capturar(page, nombre: str) -> None:
    """Deja la evidencia del ticket en verification/screenshots."""
    os.makedirs(CAPTURAS, exist_ok=True)
    page.screenshot(path=str(CAPTURAS / nombre), full_page=False)


def test_las_fechas_de_cotizaciones_se_leen_completas_en_la_tabla():
    """Lo que pidió el cliente: `Fecha Visita`, no `F. visita`."""
    with sync_playwright() as p:
        navegador = p.chromium.launch(headless=True)
        page = navegador.new_page(viewport={"width": 1400, "height": 800})
        try:
            _pantalla_montada(page)
            encabezados = page.evaluate(ENCABEZADOS_EN_PANTALLA)
            _capturar(page, "cotizaciones_fechas_con_palabra_completa.png")

            textos = [e["texto"] for e in encabezados]
            for etiqueta in ETIQUETAS_ESPERADAS.values():
                assert etiqueta in textos, (
                    f"no se ve {etiqueta!r} en la tabla; se ve: {textos}")
            abreviados = [t for t in textos if t.upper().startswith("F. ")]
            assert abreviados == [], (
                f"estas columnas siguen abreviadas para el usuario: {abreviados}")
        finally:
            navegador.close()


def test_la_etiqueta_completa_cabe_en_la_columna():
    """
    Rotular sin ensanchar deja `Fecha Vi…`: la celda recorta con elipsis.

    Es el mismo defecto para el usuario —sigue sin poder leer la palabra— con
    otro aspecto, así que se mide el recorte, no el ancho.
    """
    with sync_playwright() as p:
        navegador = p.chromium.launch(headless=True)
        page = navegador.new_page(viewport={"width": 1400, "height": 800})
        try:
            _pantalla_montada(page)
            encabezados = page.evaluate(ENCABEZADOS_EN_PANTALLA)

            recortados = [e["texto"] for e in encabezados
                          if e["recortado"] and e["texto"] in ETIQUETAS_ESPERADAS.values()]
            assert recortados == [], (
                f"la etiqueta no cabe y se ve cortada: {recortados}")
        finally:
            navegador.close()


def test_la_fila_conserva_los_nombres_de_columna_de_la_base():
    """
    El rótulo es de vista: la fila que se guarda sigue con `F. VISITA`.

    Si el cambio hubiera renombrado la clave, el valor viajaría a la base bajo
    un nombre de columna que no existe y la fecha se perdería al guardar.
    """
    with sync_playwright() as p:
        navegador = p.chromium.launch(headless=True)
        page = navegador.new_page(viewport={"width": 1400, "height": 800})
        try:
            _pantalla_montada(page)
            claves = page.evaluate(CLAVES_DE_LA_FILA)

            for columna in ETIQUETAS_ESPERADAS:
                assert columna in claves, (
                    f"la fila perdió la columna {columna!r} de la base: {claves}")
        finally:
            navegador.close()


def test_el_historial_rotula_las_fechas_igual_que_la_tabla():
    """La misma tabla se rinde en Historial; el rótulo no puede diferir."""
    with sync_playwright() as p:
        navegador = p.chromium.launch(headless=True)
        page = navegador.new_page(viewport={"width": 1400, "height": 800})
        try:
            _pantalla_montada(page, sub_vista="HISTORY")
            textos = [e["texto"] for e in page.evaluate(ENCABEZADOS_EN_PANTALLA)]

            for etiqueta in ETIQUETAS_ESPERADAS.values():
                assert etiqueta in textos, (
                    f"el historial no rotula {etiqueta!r}; se ve: {textos}")
        finally:
            navegador.close()


def test_el_monitor_de_papa_caliente_tambien_lee_las_fechas_completas():
    """
    La otra tabla de cotizaciones. Sus encabezados están escritos a mano en la
    vista, así que no los alcanza `getHeaderLabel`: si solo se hubiera tocado la
    tabla del tracker, aquí seguiría leyéndose `F. VISITA`.
    """
    with sync_playwright() as p:
        navegador = p.chromium.launch(headless=True)
        page = navegador.new_page(viewport={"width": 1400, "height": 800})
        try:
            _pantalla_montada(page, sub_vista="HOT_POTATO")
            encabezados = page.evaluate(ENCABEZADOS_EN_PANTALLA)
            _capturar(page, "papa_caliente_fechas_con_palabra_completa.png")

            textos = [e["texto"].upper() for e in encabezados]
            for columna in ETIQUETAS_ESPERADAS:
                assert columna not in textos, (
                    f"el monitor sigue abreviando {columna!r}: {textos}")
            for etiqueta in ETIQUETAS_ESPERADAS.values():
                assert etiqueta.upper() in textos, (
                    f"el monitor no rotula {etiqueta!r}; se ve: {textos}")

            recortados = [e["texto"] for e in encabezados
                          if e["recortado"] and e["texto"].upper()
                          in {v.upper() for v in ETIQUETAS_ESPERADAS.values()}]
            assert recortados == [], f"la etiqueta no cabe y se ve cortada: {recortados}"
        finally:
            navegador.close()
