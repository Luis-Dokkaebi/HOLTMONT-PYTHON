"""
Los dos desplegables del Tracker, vistos por el navegador.

`tests/test_campos_obligatorios_actividad.py` comprueba la plantilla leyendo
`index.html`; eso no distingue entre un `<select>` escrito y un `<select>` que
Vue de verdad pinta en la celda. Y el defecto que reportó el dueño era
exactamente ese: al dar de alta desde "NUEVA ACTIVIDAD" la columna de riesgo no
mostraba ningún selector.

Aquí se monta la tabla con datos y se leen las opciones del `<select>` que el
navegador acabó dibujando en cada celda.
"""

from __future__ import annotations

from playwright.sync_api import sync_playwright

BASE_URL = "http://localhost:8000"

PRIORIDADES = ["BAJA", "MEDIA", "ALTA", "URGENTE"]
RIESGOS = ["BAJO", "MEDIO", "ALTO", "CATASTROFICO"]

# La vista del Tracker, con las columnas tal como las rinde la API.
ENCABEZADOS = ["FOLIO", "CONCEPTO", "AVANCE", "FECHA_ESTIMADA_FIN", "RELOJ",
               "PRIORIDADES", "RIESGOS", "ESTATUS"]

FILA_VIEJA = {
    "FOLIO": "JO-0001", "CONCEPTO": "TAREA DE ANTES", "AVANCE": "0",
    "FECHA_ESTIMADA_FIN": "", "RELOJ": 5,
    # `ESTRATEGICA` salió del catálogo: la fila vieja tiene que seguir
    # mostrando su valor en vez de aparecer en blanco.
    "PRIORIDADES": "ESTRATEGICA", "RIESGOS": "ALTO", "ESTATUS": "ASIGNADO",
}

FILA_NUEVA = {
    "_isNew": True, "FOLIO": "", "CONCEPTO": "TAREA NUEVA", "AVANCE": "0",
    "FECHA_ESTIMADA_FIN": "", "RELOJ": 0,
    "PRIORIDADES": "", "RIESGOS": "", "ESTATUS": "",
}

MONTAR_TRACKER = """(datos) => {
    const app = document.querySelector('#app').__vue_app__._instance.proxy;
    app.isLoggedIn = true;
    app.currentUsername = 'JAIME_OLIVO';
    app.currentUser = 'JAIME OLIVO';
    app.currentView = 'STAFF_TRACKER';
    app.trackerSubView = 'TASKS';
    app.staffTracker.name = 'JAIME OLIVO';
    app.staffTracker.isLoading = false;
    app.staffTracker.headers = datos.encabezados;
    app.staffTracker.data = datos.filas;
    app.staffTracker.history = [];
}"""

# El `<select>` de una celda, buscando la fila por su concepto: la tabla se
# puede pintar en orden inverso ("Invertir Orden"), así que la posición no sirve
# de dirección.
SELECT_DE_CELDA = """([concepto, columna]) => {
    const filas = Array.from(document.querySelectorAll('.table-excel tbody tr'));
    // El concepto vive en el `value` de un `<input>`, no en el texto de la fila.
    const tr = filas.find(tr => Array.from(tr.querySelectorAll('input, textarea'))
        .some(campo => String(campo.value || '').includes(concepto)));
    if (!tr) return null;
    const sel = tr.children[columna + 1].querySelector('select');
    return sel ? { opciones: Array.from(sel.options).map(o => o.value), valor: sel.value } : null;
}"""


def _tracker_montado(page):
    page.goto(BASE_URL)
    page.wait_for_selector("#app", state="attached", timeout=15000)
    page.wait_for_function(
        "() => document.querySelector('#app') && document.querySelector('#app').__vue_app__",
        timeout=15000)
    page.evaluate(MONTAR_TRACKER, {"encabezados": ENCABEZADOS,
                                   "filas": [FILA_VIEJA, FILA_NUEVA]})
    page.wait_for_selector(".table-excel tbody tr", timeout=10000)


def test_la_actividad_nueva_tiene_desplegable_de_prioridad_y_de_riesgo():
    with sync_playwright() as p:
        navegador = p.chromium.launch(headless=True)
        page = navegador.new_page(viewport={"width": 1400, "height": 800})
        try:
            _tracker_montado(page)

            prioridad = page.evaluate(SELECT_DE_CELDA, ["TAREA NUEVA", ENCABEZADOS.index("PRIORIDADES")])
            riesgo = page.evaluate(SELECT_DE_CELDA, ["TAREA NUEVA", ENCABEZADOS.index("RIESGOS")])

            assert prioridad is not None, "la celda de PRIORIDADES no pintó ningún selector"
            assert riesgo is not None, (
                "la celda de RIESGOS no pintó ningún selector: es el defecto reportado, "
                "al dar de alta no salía el check")
            # La primera opción es el guion de "sin valor".
            assert prioridad["opciones"][1:] == PRIORIDADES, prioridad
            assert riesgo["opciones"][1:] == RIESGOS, riesgo
        finally:
            navegador.close()


def test_una_fila_vieja_conserva_el_valor_que_ya_no_esta_en_el_catalogo():
    """
    Quitar NORMAL y ESTRATEGICA del catálogo no puede vaciar filas históricas:
    un `<select>` sin la opción correspondiente se dibuja en blanco y el
    siguiente guardado borraría el dato.
    """
    with sync_playwright() as p:
        navegador = p.chromium.launch(headless=True)
        page = navegador.new_page(viewport={"width": 1400, "height": 800})
        try:
            _tracker_montado(page)

            celda = page.evaluate(SELECT_DE_CELDA, ["TAREA DE ANTES", ENCABEZADOS.index("PRIORIDADES")])
            assert "ESTRATEGICA" in celda["opciones"], celda
            assert celda["valor"] == "ESTRATEGICA", celda
        finally:
            navegador.close()
