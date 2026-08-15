"""
El tablero MÉTRICAS COT., recorrido como lo recorre Toñita.

`tests/test_agente_metricas_gemini.py` cubre el backend: qué columna da la
fecha, cómo se filtra el periodo y qué manda el cliente de Gemini. Aquí se
comprueba lo único que aquellas no pueden ver: **que los números lleguen a la
pantalla**, y que el botón EJECUTAR AGENTE mande la API key que el navegador
conserva.

Las métricas que se sirven a la vista NO están escritas a mano: se calculan con
`compute_quote_metrics` sobre filas con los encabezados reales de la hoja de
ventas. Si el backend vuelve a dejar de leer la fecha, este recorrido se apaga
igual que se apagó en producción — que es exactamente lo que una prueba de UI
con datos inventados no habría detectado.
"""

from __future__ import annotations

import json
import os
import pathlib
import sys

from playwright.sync_api import sync_playwright

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from api.services import tracker_rules as rules  # noqa: E402

BASE_URL = "http://localhost:8000"

# Cotizaciones con los encabezados que publica `QUOTE_HEADER_MAP`.
COTIZACIONES = [
    {"FOLIO": "AV-1", "CLIENTE": "ACME", "AREA": "INDUSTRIAL", "CLASIFICACION": "A",
     "VENDEDOR": "ANGEL SALINAS", "F. VISITA": "2026-06-28", "F. INICIO": "2026-07-05",
     "F. ENTREGA": "2026-07-06", "ESTATUS": "GANADA"},
    {"FOLIO": "AV-2", "CLIENTE": "BETA", "AREA": "COMERCIAL", "CLASIFICACION": "AA",
     "VENDEDOR": "TERESA GARZA", "F. VISITA": "2026-07-01", "F. INICIO": "2026-07-05",
     "F. ENTREGA": "2026-07-25", "ESTATUS": "PERDIDA X PRECIO"},
    {"FOLIO": "AV-3", "CLIENTE": "ACME", "AREA": "INDUSTRIAL", "CLASIFICACION": "AAA",
     "VENDEDOR": "ANGEL SALINAS", "F. VISITA": "2026-07-03", "F. INICIO": "2026-07-08",
     "F. ENTREGA": "2026-07-20", "ESTATUS": "GANADA"},
]

METRICAS = rules.compute_quote_metrics(COTIZACIONES, month=7, year=2026)


def _responder(route, cuerpo) -> None:
    route.fulfill(status=200, body=json.dumps(cuerpo),
                  headers={"content-type": "application/json"})


def _con_metricas_servidas(page, capturadas=None):
    """
    El backend responde con los KPIs del código real.

    La suite no toca la base de producción (`tests/conftest.py`), así que contra
    el servidor local la hoja de ventas viene vacía. Lo que se prueba aquí es la
    vista; el cálculo ya viene probado del lado de las reglas.
    """
    page.route("**/api/legacy/quoteMetrics**",
               lambda route: _responder(route, {"success": True, "metrics": METRICAS}))
    page.route("**/api/legacy/lastAgentReport**",
               lambda route: _responder(route, {"success": True, "hasReport": False, "lastRun": None}))
    page.route("**/api/legacy/geminiKey**",
               lambda route: _responder(route, {"success": True, "hasKey": False, "keyPreview": ""}))

    def agente(route):
        if capturadas is not None:
            capturadas.append(json.loads(route.request.post_data or "{}"))
        _responder(route, {"success": True, "lastRun": {
            "timestamp": "2026-08-15T12:00:00.000Z", "month": 7, "year": 2026,
            "alerts": METRICAS["alerts"], "geminiOk": True,
            "geminiSummary": "Julio cierra con 2 de 3 cotizaciones ganadas.",
            "metrics": METRICAS,
        }})

    page.route("**/api/legacy/runQuoteAgent**", agente)


def _abrir_metricas(page, key_guardada: str = "") -> None:
    """Entra al tablero como entra Toñita, sin pasar por credenciales reales."""
    page.goto(BASE_URL)
    page.wait_for_selector(".login-card", state="visible", timeout=15000)
    if key_guardada:
        page.evaluate("k => localStorage.setItem('holtmont.geminiApiKey', k)", key_guardada)
    page.evaluate(
        "() => { const app = document.querySelector('#app').__vue_app__._instance.proxy;"
        " app.isLoggedIn = true; app.currentRole = 'ADMIN';"
        " app.currentView = 'QUOTE_METRICS';"
        " app.qmFilters.month = 7; app.qmFilters.year = 2026;"
        " app.loadQuoteMetrics(); }")
    page.wait_for_selector("text=SLA POR CLASIFICACIÓN", timeout=15000)


def _capturar(page, nombre: str) -> None:
    """Deja la evidencia visual del recorrido si se pide un directorio."""
    destino = os.environ.get("HOLTMONT_UI_SHOTS", "").strip()
    if not destino:
        return
    carpeta = pathlib.Path(destino)
    carpeta.mkdir(parents=True, exist_ok=True)
    page.wait_for_timeout(1200)  # las vistas entran con `animate__fadeIn`
    page.screenshot(path=str(carpeta / f"{nombre}.png"), full_page=True)


def test_el_tablero_pinta_los_indicadores_del_periodo():
    """
    El caso que estaba roto: con la hoja llena el tablero decía "No hay
    cotizaciones terminadas registradas".
    """
    with sync_playwright() as p:
        navegador = p.chromium.launch(headless=True)
        page = navegador.new_page(viewport={"width": 1500, "height": 950})
        try:
            _con_metricas_servidas(page)
            _abrir_metricas(page)
            _capturar(page, "01_indicadores")

            assert page.locator("text=No hay cotizaciones terminadas").count() == 0
            cuerpo = page.inner_text("body")
            assert "3 cotizaciones terminadas" in cuerpo
            # 2 ganadas / 1 perdida / 67% de cierre, calculados por las reglas.
            assert METRICAS["totalCount"] == 3
            assert METRICAS["winLoss"] == {"ganada": 2, "perdida": 1, "enProceso": 0, "total": 3}
            assert "67%" in cuerpo
        finally:
            navegador.close()


def test_el_tablero_pinta_el_sla_por_clase_y_el_desglose_por_cotizador():
    with sync_playwright() as p:
        navegador = p.chromium.launch(headless=True)
        page = navegador.new_page(viewport={"width": 1500, "height": 950})
        try:
            _con_metricas_servidas(page)
            _abrir_metricas(page)
            _capturar(page, "02_sla_y_cotizadores")

            cuerpo = page.inner_text("body")
            # A: 1 día contra SLA de 3 → cumple. AA: 20 contra 14 → fuera.
            assert METRICAS["slaSummary"]["A"]["pctOk"] == 100.0
            assert METRICAS["slaSummary"]["AA"]["pctOk"] == 0.0
            assert "100%" in cuerpo and "0%" in cuerpo

            # DESEMPEÑO POR COTIZADOR: la tabla salía con las celdas en blanco
            # y "NAN%" en la columna de cierre porque la vista lee `name`,
            # `dept` y `ganadas`, claves que las reglas no publicaban.
            assert "NAN%" not in cuerpo.upper()
            fila = page.locator("table tbody tr", has_text="ANGEL SALINAS").first
            celdas = [c.strip() for c in fila.inner_text().split("\t")]
            assert celdas[0].endswith("ANGEL SALINAS")   # nombre junto al avatar
            assert celdas[1] == "INDUSTRIAL"             # departamento
            assert celdas[2:6] == ["2", "2", "0", "100%"]  # total, ✅, ❌, % cierre
            assert "TERESA GARZA" in cuerpo

            # POR DEPARTAMENTO también salía sin nombre de departamento.
            assert "INDUSTRIAL" in cuerpo and "COMERCIAL" in cuerpo

            # Panel AAA: AV-3 cerró en 12 días, dentro del SLA de 30, y ahora
            # aparece listado como proyecto del cliente.
            cliente = METRICAS["aaaByClientArr"][0]
            assert (cliente["cliente"], cliente["count"], cliente["fueraSla"]) == ("ACME", 1, 0)
            assert page.locator("text=No hay cotizaciones AAA este mes").count() == 0
            assert "AV-3" in cuerpo
        finally:
            navegador.close()


def test_ejecutar_agente_manda_la_key_que_guarda_el_navegador():
    """
    El fallo que reportó el usuario: la key se guardaba y el agente seguía
    diciendo "Sin GEMINI_API_KEY configurada", porque en Vercel la petición
    siguiente cae en otra instancia y no ve lo que la anterior dejó en memoria.
    """
    peticiones: list = []
    with sync_playwright() as p:
        navegador = p.chromium.launch(headless=True)
        page = navegador.new_page(viewport={"width": 1500, "height": 950})
        try:
            _con_metricas_servidas(page, capturadas=peticiones)
            _abrir_metricas(page, key_guardada="AIzaSyDEMO-key-de-prueba-0123456789")

            page.click("button:has-text('EJECUTAR AGENTE')")
            page.wait_for_selector("text=Agente ejecutado", timeout=15000)
            _capturar(page, "03_agente_ejecutado")

            assert peticiones == [{"month": 7, "year": 2026,
                                   "geminiKey": "AIzaSyDEMO-key-de-prueba-0123456789"}]
        finally:
            navegador.close()


def test_sin_key_guardada_el_agente_se_ejecuta_igual_con_la_del_despliegue():
    """Con `GEMINI_API_KEY` en el entorno el navegador no tiene nada que mandar."""
    peticiones: list = []
    with sync_playwright() as p:
        navegador = p.chromium.launch(headless=True)
        page = navegador.new_page(viewport={"width": 1500, "height": 950})
        try:
            _con_metricas_servidas(page, capturadas=peticiones)
            _abrir_metricas(page)

            page.click("button:has-text('EJECUTAR AGENTE')")
            page.wait_for_selector("text=Agente ejecutado", timeout=15000)

            assert peticiones == [{"month": 7, "year": 2026, "geminiKey": ""}]
        finally:
            navegador.close()
