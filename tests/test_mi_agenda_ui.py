"""
Mi Agenda pinta lo que el backend le manda.

Reporte (2026-11-19): la vista Mi Agenda salía siempre vacía —«Sin actividades
programadas» y todos los contadores en 0— aunque la persona tuviera tareas en
su tracker y eventos en su agenda personal.

La causa estaba en la frontera entre las dos mitades: `/api/legacy/unifiedAgenda`
responde `{success, workTasks, personalEvents, habits}` en la raíz, igual que
`apiFetchUnifiedAgenda` en `CODIGO.js`, y `loadPersonalAgenda` leía
`res.data.workTasks`. `res.data` no existe, el `TypeError` se tragaba dentro de
la promesa y la vista se quedaba con la agenda vacía, sin aviso.

Aquí se ejercen las dos mitades juntas: la respuesta se construye con la misma
función que sirve el endpoint (`tracker_store.fetch_unified_agenda`), con la
lectura de la base sustituida en su frontera (`read_values`), y se entrega a la
vista tal cual. Si alguna de las dos cambia la forma sin la otra, esto falla.
"""

from __future__ import annotations

import json
from typing import Any

from playwright.sync_api import sync_playwright

from api.services import tracker_store

BASE_URL = "http://localhost:8000"

PERSONA = "ANA PRUEBA AGENDA"
TAREA = "Revisión de estimación con el cliente"
EVENTO = "Llamada con proveedor de acero"

HOJAS: dict[str, list[list[Any]]] = {
    PERSONA: [
        ["FOLIO", "CONCEPTO", "CLIENTE", "FECHA", "STATUS", "AVANCE %"],
        ["CE-0001", TAREA, "PLANTA NORTE", "19/11/26", "EN PROCESO", "40"],
    ],
    "AGENDA_PERSONAL": [
        ["ID", "TITULO", "FECHA", "HORA_INICIO", "USUARIO_RAW"],
        ["ev-1", EVENTO, "19/11/26", "11:30", PERSONA],
    ],
    "HABITOS_LOG": [],
}


def _respuesta_del_backend(monkeypatch) -> dict[str, Any]:
    """Lo que `/api/legacy/unifiedAgenda` devuelve para `PERSONA`."""
    monkeypatch.setattr(tracker_store, "read_values", lambda hoja: HOJAS.get(hoja, []))
    return tracker_store.fetch_unified_agenda(PERSONA)


def test_el_backend_entrega_la_agenda_en_la_raiz_como_el_original(monkeypatch):
    """
    La forma de la respuesta es la de `apiFetchUnifiedAgenda` (CODIGO.js):
    `return { success: true, workTasks, personalEvents, habits }`. La vista
    tiene que leerla así; no se cambia el contrato para acomodar a la vista.
    """
    respuesta = _respuesta_del_backend(monkeypatch)

    assert respuesta["success"] is True
    assert "data" not in respuesta
    assert [t["CONCEPTO"] for t in respuesta["workTasks"]] == [TAREA]
    assert [e["TITULO"] for e in respuesta["personalEvents"]] == [EVENTO]
    assert respuesta["habits"] == []


def test_mi_agenda_muestra_las_tareas_y_eventos_que_manda_el_backend(monkeypatch):
    cuerpo = json.dumps(_respuesta_del_backend(monkeypatch))

    with sync_playwright() as p:
        navegador = p.chromium.launch(headless=True)
        page = navegador.new_page(viewport={"width": 1400, "height": 900})
        try:
            page.route(
                "**/api/legacy/unifiedAgenda*",
                lambda ruta: ruta.fulfill(
                    status=200, content_type="application/json", body=cuerpo
                ),
            )
            page.goto(BASE_URL)
            page.wait_for_selector(".login-card", state="visible", timeout=15000)
            page.evaluate(
                """async (persona) => {
                    const app = document.querySelector('#app').__vue_app__._instance.proxy;
                    app.config = await fetch('/api/config?role=ADMIN&username=DEMO').then(r => r.json());
                    app.currentRole = 'ADMIN';
                    app.currentUsername = 'DEMO';
                    app.currentUser = persona;
                    app.isLoggedIn = true;
                }""",
                PERSONA,
            )
            page.click(".sidebar .nav-item:has-text('Mi Agenda')")

            vista = page.locator("#pa-timeline-view")
            vista.get_by_text(TAREA).wait_for(timeout=15000)
            assert vista.get_by_text(EVENTO).is_visible()
            assert not vista.get_by_text("Sin actividades programadas").is_visible()
        finally:
            navegador.close()
