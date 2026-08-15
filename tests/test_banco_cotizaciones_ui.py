"""
El Banco de Cotizaciones, recorrido como lo recorre una persona.

`tests/test_banco_cotizaciones.py` cubre el backend: qué fecha agrupa, qué
particiones se leen y con qué nombres salen las columnas. Aquí se comprueba lo
único que aquellas no pueden ver: que al entrar por Año → Mes → Cliente →
COTIZACIONES **la tabla se pinta con las cinco columnas y con datos dentro**.

Es exactamente donde estaban los dos defectos visibles del 2026-08-15:

* la tarjeta del cliente pintaba `{{c}}` sobre un objeto `{name, count}`, así
  que en la lista de empresas salía el JSON crudo en vez del nombre;
* la columna FECHA INICIO salía vacía en todas las filas, porque la vista lee
  `file.FECHA_INICIO` y el backend respondía la fila cruda, con `F. INICIO`.
"""

from __future__ import annotations

import json
import os
import pathlib

from playwright.sync_api import sync_playwright

BASE_URL = "http://localhost:8000"

CLIENTES = [
    {"name": "DANFOSS 2", "count": 1},
    {"name": "ESSITY", "count": 2},
    {"name": "MARMON FOOD", "count": 1},
]

COTIZACIONES = [{
    "FECHA_INICIO": "01/06/26",
    "AREA": "CONSTRUCCION",
    "CONCEPTO": "FACTORY WORD",
    "VENDEDOR": "RAMIRO RODRIGUEZ",
    "ESTATUS": "ASIGNADO",
    "FOLIO": "AV-1222",
    "CLIENTE": "DANFOSS 2",
    "COTIZACION": "",
    "HOJA": "ANTONIA_VENTAS",
}]


def _con_banco_simulado(page) -> None:
    """
    El banco responde con datos fijos.

    La suite no toca la base de producción (`tests/conftest.py`), así que contra
    el servidor local el banco viene vacío; lo que se prueba aquí es la vista,
    no la consulta, y para eso hace falta que haya filas.
    """

    def responder(route, cuerpo):
        route.fulfill(status=200, body=json.dumps(cuerpo),
                      headers={"content-type": "application/json"})

    page.route("**/api/legacy/infoBankCompanies**",
               lambda route: responder(route, {"success": True, "data": CLIENTES}))
    page.route("**/api/legacy/infoBankData**",
               lambda route: responder(route, {"success": True, "data": COTIZACIONES,
                                               "headers": ["FECHA INICIO", "AREA", "CONCEPTO",
                                                           "VENDEDOR", "ESTATUS"]}))


def _abrir_banco(page) -> None:
    """Entra al Banco de Información como entra el ADMIN, sin credenciales."""
    page.goto(BASE_URL)
    page.wait_for_selector(".login-card", state="visible", timeout=15000)
    page.evaluate(
        "() => { const app = document.querySelector('#app').__vue_app__._instance.proxy;"
        " app.isLoggedIn = true; app.currentRole = 'ADMIN';"
        " app.currentView = 'INFO_BANK'; app.resetInfoBank(); }")
    page.wait_for_selector("text=Selecciona el Año", timeout=15000)


def _hasta_las_cotizaciones(page, cliente="DANFOSS 2", carpeta="COTIZACIONES") -> None:
    page.click(".btn-month:has-text('2026')")
    page.click(".btn-month:has-text('Junio')")
    page.wait_for_selector(f"text={cliente}", timeout=15000)
    page.click(f".list-group-item:has-text('{cliente}')")
    page.wait_for_selector("text=Carpetas", timeout=15000)
    page.click(f".card:has-text('{carpeta}')")
    page.wait_for_selector("table tbody tr", timeout=15000)


def _capturar(page, nombre: str) -> None:
    """Deja la evidencia visual del recorrido si se pide un directorio."""
    destino = os.environ.get("HOLTMONT_UI_SHOTS", "").strip()
    if not destino:
        return
    carpeta = pathlib.Path(destino)
    carpeta.mkdir(parents=True, exist_ok=True)
    page.wait_for_timeout(1200)  # las vistas entran con `animate__fadeIn`
    page.screenshot(path=str(carpeta / f"{nombre}.png"), full_page=True)


def test_las_empresas_del_mes_muestran_su_nombre_y_no_el_objeto():
    with sync_playwright() as p:
        navegador = p.chromium.launch(headless=True)
        page = navegador.new_page(viewport={"width": 1500, "height": 950})
        try:
            _con_banco_simulado(page)
            _abrir_banco(page)
            page.click(".btn-month:has-text('2026')")
            page.click(".btn-month:has-text('Junio')")
            page.wait_for_selector(".list-group-item", timeout=15000)
            _capturar(page, "01_empresas")

            tarjetas = page.locator(".list-group-item")
            assert tarjetas.count() == len(CLIENTES)
            texto = tarjetas.first.inner_text()
            assert "DANFOSS 2" in texto
            assert "name" not in texto and "{" not in texto, texto
        finally:
            navegador.close()


def test_la_tabla_del_cliente_pinta_las_cinco_columnas_con_datos():
    with sync_playwright() as p:
        navegador = p.chromium.launch(headless=True)
        page = navegador.new_page(viewport={"width": 1500, "height": 950})
        try:
            _con_banco_simulado(page)
            _abrir_banco(page)
            _hasta_las_cotizaciones(page)
            _capturar(page, "02_cotizaciones")

            encabezados = page.locator("table thead th").all_inner_texts()
            assert [h.strip().upper() for h in encabezados] == [
                "FECHA INICIO", "AREA", "CONCEPTO", "VENDEDOR", "ESTATUS"]

            celdas = [c.strip() for c in page.locator("table tbody tr td").all_inner_texts()]
            assert celdas[0] == "01/06/26", f"la fecha de inicio salió vacía: {celdas}"
            assert celdas[1] == "CONSTRUCCION"
            assert "FACTORY WORD" in celdas[2] and "AV-1222" in celdas[2]
            assert "RAMIRO RODRIGUEZ" in celdas[3]
            assert celdas[4] == "ASIGNADO"
        finally:
            navegador.close()


def test_el_recorrido_del_banco_no_ensucia_la_consola():
    with sync_playwright() as p:
        navegador = p.chromium.launch(headless=True)
        page = navegador.new_page(viewport={"width": 1500, "height": 950})
        errores = []
        page.on("console", lambda m: errores.append(m.text) if m.type == "error" else None)
        try:
            _con_banco_simulado(page)
            _abrir_banco(page)
            page.wait_for_timeout(800)
            basales = set(errores)

            _hasta_las_cotizaciones(page)
            page.click("button:has-text('Volver')")
            page.wait_for_selector("text=Carpetas", timeout=15000)

            nuevos = [e for e in errores if e not in basales and "favicon" not in e]
            assert not nuevos, f"El banco añadió errores de consola: {nuevos}"
        finally:
            navegador.close()
