"""El apartado Dashboard Streamlit de ANTONIO_SALAZAR, en el navegador.

Se entra con la configuración real de la cuenta (`/api/config`), se abre el
apartado desde el menú, se carga un Excel por el selector (o arrastrándolo) y se
pulsa Procesar. Lo único simulado es la red hacia fuera de la página: la URL
firmada de Supabase Storage y las respuestas de `/api/dashboard/procesar` y
`/api/dashboard/estado` (que a su vez llamarían a GitHub). El seguimiento cada
10 s se adelanta con el reloj de Playwright, no con esperas reales.
"""

from __future__ import annotations

import json
from typing import Any, Dict, List

import pytest
from playwright.sync_api import sync_playwright

BASE_URL = "http://localhost:8000"
LIGA = "https://agentefull-mhytzkjfr38ukzqxnuxbkf.streamlit.app/"
REPO = "https://github.com/Luis-py-stack/Agente_Full"
STORAGE = "https://proyecto-prueba.supabase.co/storage/v1/object/public/archivos"
SOLICITUD = "0123456789ab"
SEGUIMIENTO_MS = 10_000

EN_COLA = {"success": True, "estado": "EN_COLA", "message": "En cola en GitHub.", "url": LIGA,
           "repo_url": REPO, "run_url": ""}
PROCESANDO = {**EN_COLA, "estado": "PROCESANDO",
              "message": "Generando y validando el dashboard; tarda unos minutos."}
EXITOSO = {**EN_COLA, "estado": "EXITOSO", "message": "Dashboard generado en GitHub."}
ACEPTADO = {"success": True, "url": LIGA, "solicitud": SOLICITUD,
            "message": "El dashboard se está actualizando con ST_B2C_OCR.xlsx; tarda unos minutos."}


class Red:
    """Las respuestas de fuera de la página y lo que la página pidió."""

    def __init__(self, estados: List[Dict[str, Any]], procesar: Dict[str, Any] = ACEPTADO,
                 firma_ok: bool = True) -> None:
        self.estados = list(estados)
        self.procesar = procesar
        self.firma_ok = firma_ok
        self.subidas: List[str] = []
        self.pedidos: List[Dict[str, Any]] = []
        self.consultas: List[str] = []

    def instalar(self, page) -> None:
        page.route("**/api/legacy/uploadUrl", self._firmar)
        page.route("**/__subida_de_prueba", lambda route: route.fulfill(status=200, body=""))
        page.route("**/api/dashboard/procesar", self._procesar)
        page.route("**/api/dashboard/estado*", self._estado)

    def _firmar(self, route) -> None:
        nombre = json.loads(route.request.post_data)["name"]
        self.subidas.append(nombre)
        if not self.firma_ok:
            route.fulfill(json={"success": False, "message": "Storage no está configurado."})
            return
        route.fulfill(json={"success": True, "uploadUrl": f"{BASE_URL}/__subida_de_prueba",
                            "fileUrl": f"{STORAGE}/{nombre}", "maxBytes": 10_000_000})

    def _procesar(self, route) -> None:
        self.pedidos.append(json.loads(route.request.post_data))
        route.fulfill(json=self.procesar)

    def _estado(self, route) -> None:
        self.consultas.append(route.request.url)
        respuesta = self.estados.pop(0) if len(self.estados) > 1 else self.estados[0]
        route.fulfill(json=respuesta)


@pytest.fixture
def abrir_apartado():
    with sync_playwright() as p:
        navegador = p.chromium.launch(headless=True)

        def abrir(red: Red, cuenta: str = "ANTONIO_SALAZAR", role: str = "STAFF_USER"):
            page = navegador.new_page(viewport={"width": 1400, "height": 900})
            page.clock.install()
            red.instalar(page)
            page.goto(BASE_URL)
            page.wait_for_selector(".login-card", state="visible", timeout=20000)
            page.evaluate(
                """async ([role, username]) => {
                    const app = document.querySelector('#app').__vue_app__._instance.proxy;
                    app.config = await fetch(`/api/config?role=${role}&username=${username}`).then(r => r.json());
                    app.currentRole = role;
                    app.currentUsername = username;
                    app.isLoggedIn = true;
                }""",
                [role, cuenta],
            )
            page.wait_for_selector(".nav-item", timeout=15000)
            return page

        try:
            yield abrir
        finally:
            navegador.close()


def _entrar_al_apartado(page) -> None:
    page.locator(".nav-item", has_text="Dashboard Streamlit").click()
    page.wait_for_selector("#vistaDashboardStreamlit", timeout=10000)


def _cargar(page, nombre: str = "ST_B2C_OCR.xlsx") -> None:
    page.set_input_files("#inputDashboardStreamlit", {"name": nombre, "mimeType": "application/octet-stream",
                                                       "buffer": b"PK\x03\x04hoja"})


def _esperar_texto(page, selector: str, texto: str) -> None:
    page.wait_for_function(
        "([s, t]) => { const e = document.querySelector(s); return !!e && e.innerText.includes(t); }",
        arg=[selector, texto], timeout=10000)


def _esperar_respuesta_de_procesar(page) -> None:
    """
    Espera a que la página tenga la respuesta de `/procesar` antes de adelantar
    el reloj.

    "Cargando..." sale ANTES de esa respuesta (`procesarDashboardStreamlit` pone
    la fase PROCESANDO y luego hace el `await`), y el seguimiento cada 10 s se
    programa DESPUÉS. Si el reloj se adelanta en ese hueco, el temporizador
    queda para 10 s reales más tarde y la espera siguiente vence justo antes:
    pasaba en CI bajo carga (corridas 40949065308 y 40951195497). El mensaje de
    `/procesar` se escribe en el mismo bloque que programa el temporizador, así
    que verlo en pantalla garantiza que ya está programado.
    """
    _esperar_texto(page, "#estadoDashboardStreamlit", ACEPTADO["message"])


def test_antonio_abre_el_apartado_desde_el_menu(abrir_apartado):
    page = abrir_apartado(Red([EN_COLA]))

    _entrar_al_apartado(page)

    assert page.locator(".top-bar h6").inner_text() == "DASHBOARD STREAMLIT"
    assert page.locator("#zonaDashboardStreamlit").is_visible()
    assert page.locator("#botonProcesarDashboardStreamlit").count() == 0


def test_quien_no_tiene_la_bandera_no_ve_el_apartado(abrir_apartado):
    page = abrir_apartado(Red([EN_COLA]), cuenta="TERESA_GARZA")

    assert page.locator(".nav-item", has_text="Agregar Actividad").count() == 1
    assert page.locator(".nav-item", has_text="Dashboard Streamlit").count() == 0


def test_cargar_el_excel_procesarlo_y_recibir_la_liga(abrir_apartado):
    red = Red([EN_COLA, PROCESANDO, EXITOSO])
    page = abrir_apartado(red)
    _entrar_al_apartado(page)

    _cargar(page)
    boton = page.locator("#botonProcesarDashboardStreamlit")
    page.wait_for_function("() => { const b = document.querySelector('#botonProcesarDashboardStreamlit');"
                           " return b && !b.disabled; }", timeout=10000)

    assert red.subidas == ["ST_B2C_OCR.xlsx"]
    assert page.locator("#nombreArchivoDashboardStreamlit").inner_text() == "ST_B2C_OCR.xlsx"
    assert boton.inner_text().strip() == "Procesar"

    boton.click()
    page.wait_for_selector("text=Cargando...", timeout=10000)
    _esperar_respuesta_de_procesar(page)
    assert red.pedidos == [{"fileUrl": f"{STORAGE}/ST_B2C_OCR.xlsx", "usuario": "ANTONIO_SALAZAR"}]
    assert boton.is_disabled()

    page.clock.fast_forward(SEGUIMIENTO_MS)
    _esperar_texto(page, "#estadoDashboardStreamlit", "En cola en GitHub.")
    page.clock.fast_forward(SEGUIMIENTO_MS)
    _esperar_texto(page, "#estadoDashboardStreamlit", "Generando y validando")
    page.clock.fast_forward(SEGUIMIENTO_MS)
    page.wait_for_selector("#exitoDashboardStreamlit", timeout=10000)

    assert all(c.endswith(f"/api/dashboard/estado?solicitud={SOLICITUD}") for c in red.consultas)
    exito = page.locator("#exitoDashboardStreamlit")
    assert "¡Procesamiento Exitoso!" in exito.inner_text()
    assert "Dashboard generado en GitHub." in exito.inner_text()
    assert REPO in exito.inner_text()
    abrir = page.locator("#botonAbrirStreamlit")
    assert abrir.inner_text().strip() == "Abrir en Streamlit"
    assert abrir.get_attribute("href") == LIGA
    assert abrir.get_attribute("target") == "_blank"
    assert page.locator("#barraDashboardStreamlit").get_attribute("aria-valuenow") == "100"
    assert page.locator("text=Cargando...").count() == 0


def test_arrastrar_el_excel_a_la_zona_lo_carga(abrir_apartado):
    red = Red([EN_COLA])
    page = abrir_apartado(red)
    _entrar_al_apartado(page)

    transferencia = page.evaluate_handle("""() => {
        const dt = new DataTransfer();
        dt.items.add(new File(['PK'], 'Junta HLT.xlsx'));
        return dt;
    }""")
    page.dispatch_event("#zonaDashboardStreamlit", "dragover", {"dataTransfer": transferencia})
    page.dispatch_event("#zonaDashboardStreamlit", "drop", {"dataTransfer": transferencia})
    page.wait_for_function("() => { const b = document.querySelector('#botonProcesarDashboardStreamlit');"
                           " return b && !b.disabled; }", timeout=10000)

    assert red.subidas == ["Junta HLT.xlsx"]
    assert page.locator("#nombreArchivoDashboardStreamlit").inner_text() == "Junta HLT.xlsx"


def test_un_archivo_que_no_es_excel_se_rechaza_sin_subirlo(abrir_apartado):
    red = Red([EN_COLA])
    page = abrir_apartado(red)
    _entrar_al_apartado(page)

    _cargar(page, "fachada.jpg")
    page.wait_for_selector("#errorDashboardStreamlit", timeout=10000)

    assert "fachada.jpg no es un archivo de Excel" in page.locator("#errorDashboardStreamlit").inner_text()
    assert red.subidas == []
    assert page.locator("#botonProcesarDashboardStreamlit").count() == 0


def test_si_la_subida_falla_se_avisa_y_no_se_puede_procesar(abrir_apartado):
    red = Red([EN_COLA], firma_ok=False)
    page = abrir_apartado(red)
    _entrar_al_apartado(page)

    _cargar(page)
    _esperar_texto(page, "#errorDashboardStreamlit", "Storage no está configurado.")

    assert page.locator("#botonProcesarDashboardStreamlit").count() == 0
    assert red.pedidos == []


def test_doble_clic_en_procesar_manda_un_solo_pedido(abrir_apartado):
    red = Red([EN_COLA])
    page = abrir_apartado(red)
    _entrar_al_apartado(page)
    _cargar(page)
    page.wait_for_function("() => { const b = document.querySelector('#botonProcesarDashboardStreamlit');"
                           " return b && !b.disabled; }", timeout=10000)

    page.locator("#botonProcesarDashboardStreamlit").dblclick()
    page.wait_for_selector("text=Cargando...", timeout=10000)
    page.wait_for_timeout(300)

    assert len(red.pedidos) == 1


def test_si_no_se_puede_procesar_se_dice_por_que_y_se_puede_reintentar(abrir_apartado):
    falla = {"success": False, "url": LIGA, "message": "Falta configurar DASHBOARD_PWO_TOKEN en el despliegue."}
    red = Red([EN_COLA], procesar=falla)
    page = abrir_apartado(red)
    _entrar_al_apartado(page)
    _cargar(page)
    page.wait_for_function("() => { const b = document.querySelector('#botonProcesarDashboardStreamlit');"
                           " return b && !b.disabled; }", timeout=10000)

    page.locator("#botonProcesarDashboardStreamlit").click()
    _esperar_texto(page, "#errorDashboardStreamlit", "DASHBOARD_PWO_TOKEN")

    assert page.locator("#botonProcesarDashboardStreamlit").is_enabled()
    red.procesar = ACEPTADO
    page.locator("#botonProcesarDashboardStreamlit").click()
    page.wait_for_selector("text=Cargando...", timeout=10000)
    assert len(red.pedidos) == 2
    assert page.locator("#errorDashboardStreamlit").count() == 0


def test_un_dashboard_que_no_pasa_las_pruebas_se_avisa(abrir_apartado):
    error = {**EN_COLA, "estado": "ERROR",
             "message": "El dashboard no pasó las pruebas o el Action falló; la liga sigue mostrando el dashboard anterior."}
    red = Red([PROCESANDO, error])
    page = abrir_apartado(red)
    _entrar_al_apartado(page)
    _cargar(page)
    page.wait_for_function("() => { const b = document.querySelector('#botonProcesarDashboardStreamlit');"
                           " return b && !b.disabled; }", timeout=10000)

    page.locator("#botonProcesarDashboardStreamlit").click()
    page.wait_for_selector("text=Cargando...", timeout=10000)
    _esperar_respuesta_de_procesar(page)
    page.clock.fast_forward(SEGUIMIENTO_MS)
    _esperar_texto(page, "#estadoDashboardStreamlit", "Generando y validando")
    page.clock.fast_forward(SEGUIMIENTO_MS)
    _esperar_texto(page, "#errorDashboardStreamlit", "dashboard anterior")

    assert page.locator("#exitoDashboardStreamlit").count() == 0
    assert page.locator("text=Cargando...").count() == 0


def test_si_github_nunca_arranca_se_avisa_en_vez_de_cargar_para_siempre(abrir_apartado):
    sin_iniciar = {**EN_COLA, "estado": "SIN_INICIAR", "message": "Esperando a que GitHub arranque el procesamiento."}
    red = Red([sin_iniciar])
    page = abrir_apartado(red)
    _entrar_al_apartado(page)
    _cargar(page)
    page.wait_for_function("() => { const b = document.querySelector('#botonProcesarDashboardStreamlit');"
                           " return b && !b.disabled; }", timeout=10000)

    page.locator("#botonProcesarDashboardStreamlit").click()
    page.wait_for_selector("text=Cargando...", timeout=10000)
    _esperar_respuesta_de_procesar(page)
    page.clock.fast_forward(SEGUIMIENTO_MS)
    _esperar_texto(page, "#estadoDashboardStreamlit", "Esperando a que GitHub")
    page.clock.fast_forward(4 * 60 * 1000)
    _esperar_texto(page, "#errorDashboardStreamlit", "GitHub no arrancó el procesamiento")


def test_si_no_se_puede_consultar_tres_veces_seguidas_se_avisa(abrir_apartado):
    caida = {"success": False, "url": LIGA, "repo_url": REPO, "message": "No se pudo consultar a GitHub: timed out"}
    red = Red([caida])
    page = abrir_apartado(red)
    _entrar_al_apartado(page)
    _cargar(page)
    page.wait_for_function("() => { const b = document.querySelector('#botonProcesarDashboardStreamlit');"
                           " return b && !b.disabled; }", timeout=10000)

    page.locator("#botonProcesarDashboardStreamlit").click()
    page.wait_for_selector("text=Cargando...", timeout=10000)
    _esperar_respuesta_de_procesar(page)
    for intento in (1, 2):
        page.clock.fast_forward(SEGUIMIENTO_MS)
        _esperar_texto(page, "#estadoDashboardStreamlit", f"({intento}/3)")
    page.clock.fast_forward(SEGUIMIENTO_MS)
    _esperar_texto(page, "#errorDashboardStreamlit", "timed out")

    assert len(red.consultas) == 3
