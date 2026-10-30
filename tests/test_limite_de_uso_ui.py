"""
El aviso de «Límite de uso» visto en el navegador.

`tests/test_limite_de_uso.py` cubre cuándo el backend lo decide. Aquí se
comprueba lo que pidió el dueño (2026-10-30): que lo vean **los dos**, quien
va a iniciar sesión y quien ya la tenía abierta cuando se desconectó la base.

El segundo caso es el que falla callado: una página que solo consulta al
cargar deja a quien ya estaba dentro trabajando contra una base que no existe
hasta que recargue, y nadie recarga. Por eso el aviso se vuelve a consultar
cada minuto, y el reloj se adelanta con `page.clock` en vez de esperar (R8).
"""

from __future__ import annotations

import json

from playwright.sync_api import sync_playwright

BASE_URL = "http://localhost:8000"

MENSAJE = (
    "Límite de uso agotado por insuficiencia de espacio en base de datos. "
    "La plataforma detectó que el almacenamiento contratado ya no es suficiente "
    "para el volumen de datos del proyecto."
)

SIN_BASE = {"success": True, "disponible": False, "mensaje": MENSAJE}
CON_BASE = {"success": True, "disponible": True, "mensaje": ""}


def _doblar_estado(page, estado: dict) -> None:
    """Sustituye `/api/estado`; se cambia mutando `estado` a mitad de la prueba."""
    page.route("**/api/estado", lambda ruta: ruta.fulfill(
        status=200, content_type="application/json", body=json.dumps(estado)))


def _entrar(page) -> None:
    """Sesión abierta con la configuración real de ADMIN, sin pasar por credenciales."""
    page.wait_for_selector(".login-card", state="visible", timeout=15000)
    page.evaluate(
        """async () => {
            const app = document.querySelector('#app').__vue_app__._instance.proxy;
            app.config = await fetch('/api/config?role=ADMIN&username=LUIS_CARLOS')
                .then(r => r.json());
            app.currentRole = 'ADMIN';
            app.currentUsername = 'LUIS_CARLOS';
            app.isLoggedIn = true;
        }"""
    )
    page.wait_for_selector(".nav-item", timeout=15000)


def _aviso_tapa_el_centro(page) -> bool:
    """Lo que hay en el centro de la pantalla es el aviso, no lo de debajo."""
    return page.evaluate(
        """() => {
            const el = document.elementFromPoint(innerWidth / 2, innerHeight / 2);
            return !!(el && el.closest('#limiteDeUso'));
        }"""
    )


def test_quien_va_a_entrar_ve_limite_de_uso_encima_del_login():
    with sync_playwright() as p:
        navegador = p.chromium.launch(headless=True)
        page = navegador.new_page(viewport={"width": 1400, "height": 900})
        try:
            _doblar_estado(page, dict(SIN_BASE))
            page.goto(BASE_URL)
            page.wait_for_selector("#limiteDeUso", state="visible", timeout=15000)
            assert page.inner_text("#limiteDeUso").strip() == MENSAJE
            assert _aviso_tapa_el_centro(page)
        finally:
            navegador.close()


def test_quien_ya_tenia_sesion_ve_el_aviso_en_la_siguiente_consulta():
    with sync_playwright() as p:
        navegador = p.chromium.launch(headless=True)
        page = navegador.new_page(viewport={"width": 1400, "height": 900})
        try:
            estado = dict(CON_BASE)
            page.clock.install()
            _doblar_estado(page, estado)
            page.goto(BASE_URL)
            _entrar(page)
            assert page.locator("#limiteDeUso").is_hidden()

            estado.update(SIN_BASE)   # se borran las variables en el despliegue
            page.clock.fast_forward("01:01")
            page.wait_for_selector("#limiteDeUso", state="visible", timeout=5000)
            assert page.inner_text("#limiteDeUso").strip() == MENSAJE
            assert _aviso_tapa_el_centro(page)
        finally:
            navegador.close()


def test_al_volver_la_base_el_aviso_se_retira_solo():
    with sync_playwright() as p:
        navegador = p.chromium.launch(headless=True)
        page = navegador.new_page(viewport={"width": 1400, "height": 900})
        try:
            estado = dict(SIN_BASE)
            page.clock.install()
            _doblar_estado(page, estado)
            page.goto(BASE_URL)
            page.wait_for_selector("#limiteDeUso", state="visible", timeout=15000)

            estado.update(CON_BASE)
            page.clock.fast_forward("01:01")
            page.wait_for_selector("#limiteDeUso", state="hidden", timeout=5000)
            assert page.locator(".login-card").is_visible()
        finally:
            navegador.close()


def test_si_la_consulta_falla_no_se_bloquea_la_plataforma():
    """Un corte de red no es una base desconectada: sin respuesta, no hay aviso."""
    with sync_playwright() as p:
        navegador = p.chromium.launch(headless=True)
        page = navegador.new_page(viewport={"width": 1400, "height": 900})
        try:
            page.route("**/api/estado", lambda ruta: ruta.abort())
            page.goto(BASE_URL)
            page.wait_for_selector(".login-card", state="visible", timeout=15000)
            page.wait_for_timeout(500)
            assert page.locator("#limiteDeUso").is_hidden()
        finally:
            navegador.close()


def test_con_la_base_de_la_suite_no_aparece_el_aviso():
    """Sin doble: el servidor real de la suite (motor en memoria) tiene base."""
    with sync_playwright() as p:
        navegador = p.chromium.launch(headless=True)
        page = navegador.new_page(viewport={"width": 1400, "height": 900})
        try:
            with page.expect_response("**/api/estado") as respuesta:
                page.goto(BASE_URL)
            assert respuesta.value.json()["disponible"] is True
            page.wait_for_selector(".login-card", state="visible", timeout=15000)
            assert page.locator("#limiteDeUso").is_hidden()
        finally:
            navegador.close()
