"""El botón DASHBOARD de la Pre Work Order, en el navegador.

Se sube un archivo por el selector real de la PWO y se mira qué pasa en la
pantalla. Lo único simulado es la red hacia fuera de la página: la URL firmada
de Supabase Storage y la respuesta de `/api/pwo/dashboard` (que a su vez
llamaría a GitHub). Así se prueba lo que le toca al formulario: qué archivos
piden dashboard, qué viaja al servidor y qué ve el cotizador.
"""

from __future__ import annotations

import json
from typing import Any, Dict, List

import pytest
from playwright.sync_api import sync_playwright

BASE_URL = "http://localhost:8000"
LIGA = "https://holtmont-pwo.streamlit.app"
STORAGE = "https://proyecto-prueba.supabase.co/storage/v1/object/public/archivos"
APP = "document.querySelector('#app').__vue_app__._instance.proxy"


def _preparar_red(page, respuesta_post: Dict[str, Any], pedidos: List[Dict[str, Any]]) -> None:
    def subida_firmada(route):
        nombre = json.loads(route.request.post_data)["name"]
        route.fulfill(json={"success": True, "uploadUrl": f"{BASE_URL}/__subida_de_prueba",
                            "fileUrl": f"{STORAGE}/{nombre}", "maxBytes": 10_000_000})

    def dashboard(route):
        if route.request.method == "GET":
            route.fulfill(json={"success": True, "url": LIGA, "configurado": True})
            return
        pedidos.append(json.loads(route.request.post_data))
        route.fulfill(json=respuesta_post)

    page.route("**/api/legacy/uploadUrl", subida_firmada)
    page.route("**/__subida_de_prueba", lambda route: route.fulfill(status=200, body=""))
    page.route("**/api/pwo/dashboard", dashboard)


@pytest.fixture
def abrir_pwo():
    with sync_playwright() as p:
        navegador = p.chromium.launch(headless=True)

        def abrir(respuesta_post: Dict[str, Any], pedidos: List[Dict[str, Any]]):
            page = navegador.new_page(viewport={"width": 1500, "height": 950})
            _preparar_red(page, respuesta_post, pedidos)
            page.goto(BASE_URL)
            page.wait_for_selector(".login-card", state="visible", timeout=20000)
            page.evaluate(f"() => {{ const app = {APP}; app.isLoggedIn = true;"
                          " app.currentUsername = 'PREWORK_ORDER'; app.currentView = 'WORKORDER_FORM'; }")
            page.wait_for_selector("#campoConcepto", timeout=20000)
            return page

        try:
            yield abrir
        finally:
            navegador.close()


def _subir(page, nombre: str) -> None:
    selector = page.evaluate_handle(f"() => {APP}.fileInput")
    selector.as_element().set_input_files({"name": nombre, "mimeType": "application/octet-stream",
                                           "buffer": b"contenido"})
    page.wait_for_selector(".swal2-title:has-text('Archivo Subido')", timeout=10000)


def test_el_boton_abre_la_liga_corta_al_entrar_a_la_pwo(abrir_pwo):
    page = abrir_pwo({"success": True}, [])

    boton = page.locator("#botonDashboardPwo")
    boton.wait_for(timeout=10000)
    page.wait_for_function("() => document.querySelector('#botonDashboardPwo').getAttribute('href')")

    assert boton.get_attribute("href") == LIGA
    assert boton.get_attribute("target") == "_blank"
    assert "disabled" not in (boton.get_attribute("class") or "")


def test_subir_una_hoja_de_calculo_pide_el_dashboard_con_ese_archivo(abrir_pwo):
    pedidos: List[Dict[str, Any]] = []
    mensaje = "El dashboard se está actualizando con Junta HLT.xlsx; tarda unos minutos."
    page = abrir_pwo({"success": True, "url": LIGA, "message": mensaje}, pedidos)

    _subir(page, "Junta HLT.xlsx")
    page.wait_for_selector("#estadoDashboardPwo", timeout=10000)
    page.wait_for_function("() => document.querySelector('#estadoDashboardPwo').innerText.includes('tarda unos minutos')")

    assert pedidos == [{"fileUrl": f"{STORAGE}/Junta HLT.xlsx", "folio": "", "usuario": "PREWORK_ORDER"}]
    estado = page.locator("#estadoDashboardPwo")
    assert estado.inner_text() == mensaje
    assert "text-danger" not in (estado.get_attribute("class") or "")


def test_una_foto_de_la_obra_no_toca_el_dashboard(abrir_pwo):
    pedidos: List[Dict[str, Any]] = []
    page = abrir_pwo({"success": True, "url": LIGA, "message": "no debería llegar"}, pedidos)

    _subir(page, "fachada.jpg")
    page.wait_for_timeout(500)

    assert pedidos == []
    assert page.locator("#estadoDashboardPwo").count() == 0


def test_si_no_se_puede_pedir_el_dashboard_se_avisa_junto_al_boton(abrir_pwo):
    pedidos: List[Dict[str, Any]] = []
    falla = {"success": False, "url": LIGA, "message": "Falta configurar DASHBOARD_PWO_TOKEN en el despliegue."}
    page = abrir_pwo(falla, pedidos)

    _subir(page, "costos.csv")
    page.wait_for_function("() => { const e = document.querySelector('#estadoDashboardPwo');"
                           " return e && e.innerText.includes('DASHBOARD_PWO_TOKEN'); }", timeout=10000)

    estado = page.locator("#estadoDashboardPwo")
    assert estado.inner_text() == falla["message"]
    assert "text-danger" in (estado.get_attribute("class") or "")
    assert len(pedidos) == 1
