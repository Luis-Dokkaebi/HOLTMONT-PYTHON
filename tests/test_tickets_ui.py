"""
El reporte de bugs, recorrido como lo recorre una persona.

`tests/test_backend_tickets.py` cubre el contrato del backend. Aquí se
comprueba lo único que aquellas no pueden ver: que cuando el backend
responde con un error, la persona **puede leerlo y seguir usando la
pantalla**.

Es la parte que falló de verdad. El 2026-08-13 el dueño intentó reportar un
bug con la tabla `bug_tickets` sin crear y se topó con dos defectos a la vez:

1. el backend le devolvió el texto crudo del motor
   (`PostgREST GET bug_tickets?select=folio&offset=0&limit=1000 respondió
   404`), que no le dice qué hacer;
2. ese aviso salía por SweetAlert2, que se dibuja en z-index 1060, detrás
   del modal de tickets que está en 2500 — el botón "OK" quedaba
   inalcanzable y el diálogo, trabado.

El segundo es el que estas pruebas fijan: con el arreglo el error se
muestra dentro del modal y la pantalla sigue viva.
"""

from __future__ import annotations

import json

from playwright.sync_api import sync_playwright

BASE_URL = "http://localhost:8000"

MENSAJE_503 = (
    "El sistema de tickets todavía no está instalado en la base de datos: "
    "falta crear la tabla `bug_tickets`. Aplicar el DDL de docs/DDL_PENDIENTE.sql §5."
)

TICKET_DE_EJEMPLO = {
    "id": "1", "folio": "BUG-0001", "reportado_por": "TERESA GARZA", "modulo": "PPC",
    "descripcion": "El filtro semanal no guarda la fecha", "severidad": "ALTA",
    "estatus": "ABIERTO", "evidencia": [], "created_at": "2026-08-13T12:00:00Z",
}


def _responder(route, estado: int, cuerpo: dict) -> None:
    route.fulfill(status=estado, body=json.dumps(cuerpo),
                  headers={"content-type": "application/json"})


def _con_backend_en_error(page) -> None:
    """Intercepta `/api/v2/tickets` para simular los fallos reales del motor."""

    def manejar(route):
        metodo = route.request.method
        if metodo == "POST":
            _responder(route, 503, {"detail": MENSAJE_503})
        elif metodo == "PATCH":
            _responder(route, 502, {"detail": "No se pudo consultar el sistema de tickets."})
        else:
            _responder(route, 200, {"success": True, "count": 1, "data": [TICKET_DE_EJEMPLO]})

    page.route("**/api/v2/tickets**", manejar)


def test_el_error_al_reportar_se_lee_y_no_deja_la_pantalla_trabada():
    """
    El defecto: el aviso salía detrás del modal y su botón no se podía pulsar.

    Se comprueban las tres cosas que definen "no trabado": el error es
    legible, no queda ningún SweetAlert2 encima, y el modal se puede cerrar.
    """
    with sync_playwright() as p:
        navegador = p.chromium.launch(headless=True)
        page = navegador.new_page(viewport={"width": 1280, "height": 900})
        try:
            _con_backend_en_error(page)
            page.goto(BASE_URL)
            page.wait_for_selector("#bug-ticket-fab", state="visible", timeout=15000)

            page.click("#bug-ticket-fab")
            page.fill("#bt-descripcion", "El avance no se guarda")
            page.click("#bt-enviar")

            page.wait_for_selector("#bt-error", state="visible", timeout=5000)
            texto = page.inner_text("#bt-error")
            assert "bug_tickets" in texto, f"el error no dice qué falta: {texto!r}"

            assert page.locator(".swal2-container").count() == 0, (
                "el error salió por SweetAlert2: queda detrás del modal (z-index 1060 vs 2500) "
                "y su botón OK es inalcanzable"
            )
            assert not page.is_disabled("#bt-enviar"), "el botón quedó bloqueado tras el error"

            page.click("#bt-cancelar")
            assert "open" not in (page.get_attribute("#bug-ticket-overlay", "class") or ""), (
                "el modal no se pudo cerrar después del error"
            )
        finally:
            navegador.close()


def test_el_error_al_resolver_un_ticket_tampoco_traba_el_panel():
    """Mismo defecto y mismo arreglo en el panel de soporte."""
    with sync_playwright() as p:
        navegador = p.chromium.launch(headless=True)
        page = navegador.new_page(viewport={"width": 1280, "height": 900})
        try:
            _con_backend_en_error(page)
            page.goto(BASE_URL)
            page.wait_for_selector("#bug-ticket-fab", state="visible", timeout=15000)

            # Sesión de soporte sin pasar por credenciales reales, igual que
            # hace `test_plano_2d_ui.py` para entrar a la Pre Work Order.
            page.evaluate(
                "() => { window.app.currentUsername = 'LUIS_CARLOS';"
                " window.app.config = { canManageTickets: true }; }")
            page.wait_for_selector("#tickets-soporte-fab", state="visible", timeout=5000)

            page.click("#tickets-soporte-fab")
            page.wait_for_selector(".ts-card", timeout=5000)
            page.select_option(".ts-card .ts-estatus", "EN_REVISION")
            page.click(".ts-card .ts-guardar")

            page.wait_for_selector(".ts-card .ts-error", state="visible", timeout=5000)
            assert page.locator(".swal2-container").count() == 0, (
                "el error salió por SweetAlert2 y queda detrás del panel"
            )
            assert not page.is_disabled(".ts-card .ts-guardar"), (
                "el botón Guardar quedó bloqueado tras el error"
            )
        finally:
            navegador.close()
