"""
Revela las capturas del modal «Asignar Vendedor / Empleado».

Reporte del dueño (2026-08-18), con captura: desde `ANTONIA_VENTAS` el modal de
la columna VENDEDOR ofrecía a los 40 del directorio. Una cotización solo puede
caer en una tabla `<NOMBRE> (VENTAS)`, así que elegir ahí a alguien sin tabla
guardaba la fila sin error y sin copia. Desde un tracker no aplica: ahí se
reparte una actividad y todo el mundo tiene tracker.

Esto no es una prueba: las que bloquean viven en la suite
(`tests/test_lista_de_asignables.py` evalúa con Node el `staffToUse` real de
`openVendorSelector`, y hay dos escenarios Gherkin en
`tests/features/asignacion_de_cotizaciones.feature`). Aquí solo se revelan las
fotos.

Se entra con el formulario de login real, así que el `directory` y su bandera
`sales` los rinde el backend. Lo único que se inyecta es el **contenido de la
tabla** —encabezados y una fila—, porque el motor `memoria` no trae
cotizaciones; la lista del modal la arma la vista con el directorio de verdad.

    BACKEND_ENGINE=memoria \\
    DEV_LOGIN_USERS='ANTONIA_VENTAS:<clave>:TONITA:Antonia Pineda' \\
    PYTHONPATH=. python3 api/main.py &
    DEMO_PASSWORD=<clave> python3 verification/verify_modal_asignacion_ventas.py [URL]

La contraseña la fija quien levanta el servidor y solo vive en esas dos
variables de entorno: este archivo no la trae escrita.
"""

from __future__ import annotations

import os
import pathlib
import sys

RAIZ = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(RAIZ))

from playwright.sync_api import sync_playwright  # noqa: E402

from tests import conftest  # noqa: E402
from tests.test_alta_cotizaciones_ui import (  # noqa: E402
    ENCABEZADOS_COTIZACIONES,
    MONTAR,
    _cotizacion,
)

DESTINO = pathlib.Path(__file__).resolve().parent
CUENTA = "ANTONIA_VENTAS"

# Una fila de tracker con la columna RESPONSABLE, que abre el mismo modal.
ENCABEZADOS_TRACKER = ["FOLIO", "CONCEPTO", "RESPONSABLE", "AVANCE", "ESTATUS"]
FILA_TRACKER = {"FOLIO": "AS-0001", "CONCEPTO": "REVISAR PLANOS",
                "RESPONSABLE": "", "AVANCE": "0", "ESTATUS": "PENDIENTE"}

# Los nombres que el modal deja ver, en el orden en que los pinta.
NOMBRES_DEL_MODAL = """() => Array.from(
    document.querySelectorAll('#swal-checkbox-list .employee-item'))
    .map(el => el.querySelector('label').textContent.trim())"""

CERRAR = """() => { if (window.Swal) Swal.close(); }"""


def _entrar(page, base_url: str, clave: str) -> None:
    page.goto(base_url)
    page.wait_for_selector(".login-card", state="visible", timeout=20000)
    page.fill('.login-card input[placeholder="Usuario"]', CUENTA)
    page.fill('.login-card input[placeholder="Contraseña..."]', clave)
    page.click(".login-card button.btn-outline-light")
    page.wait_for_selector(".app-wrapper", state="visible", timeout=20000)
    # El directorio llega con `getSystemConfig`; sin él el modal saldría vacío y
    # la captura no probaría nada.
    page.wait_for_function(
        "() => (document.querySelector('#app').__vue_app__._instance.proxy"
        ".config.directory || []).length > 0", timeout=20000)


def _abrir_modal(page, hoja: str, encabezados: list, fila: dict,
                 columna: str, archivo: str) -> list:
    page.evaluate(MONTAR, {"hoja": hoja, "usuario": CUENTA,
                           "encabezados": encabezados, "filas": [dict(fila)]})
    page.wait_for_selector(".table-excel tbody tr", timeout=15000)

    rotulos = [t.strip().upper()
               for t in page.locator("table.table-excel thead th").all_inner_texts()]
    # La cabecera trae `#` como primera columna, igual que el cuerpo, así que
    # el índice del rótulo es el mismo de la celda.
    indice = next(i for i, t in enumerate(rotulos) if columna in t)
    page.locator("table.table-excel tbody tr").first.locator("td").nth(indice).click()

    page.wait_for_selector("#swal-checkbox-list .employee-item", timeout=15000)
    page.wait_for_timeout(400)
    page.screenshot(path=str(DESTINO / archivo))

    nombres = page.evaluate(NOMBRES_DEL_MODAL)
    titulo = page.locator(".swal2-title").inner_text().strip()
    print(f"  {hoja} · «{titulo}» · {len(nombres)} personas")
    print(f"    {nombres}")
    page.evaluate(CERRAR)
    page.wait_for_timeout(400)
    return nombres


def main(base_url: str) -> int:
    clave = os.environ.get("DEMO_PASSWORD", "").strip()
    if not clave:
        print("Falta DEMO_PASSWORD: la misma contraseña que pusiste en "
              "DEV_LOGIN_USERS al levantar el servidor.")
        return 2

    # Sirve las CDNs desde el cache en disco (ver tests/conftest.py).
    conftest.pytest_configure(None)

    with sync_playwright() as p:
        navegador = p.chromium.launch(headless=True)
        page = navegador.new_page(viewport={"width": 1400, "height": 800})
        try:
            _entrar(page, base_url, clave)

            vendedores = _abrir_modal(
                page, "ANTONIA_VENTAS", ENCABEZADOS_COTIZACIONES,
                _cotizacion("tmp-modal", "ACME", "COTIZAR NAVE"),
                "VENDEDOR", "modal_ventas_01_solo_vendedores.png")

            empleados = _abrir_modal(
                page, "JAIME OLIVO", ENCABEZADOS_TRACKER, FILA_TRACKER,
                "RESPONSABLE", "modal_ventas_02_tracker_todos.png")

            con_tabla = [p_["name"] for p_ in
                         page.evaluate("() => document.querySelector('#app')"
                                       ".__vue_app__._instance.proxy.config.directory")
                         if p_.get("sales")]

            if sorted(vendedores) != sorted(con_tabla):
                print(f"  FALLA: la tabla de ventas ofrece {vendedores}, "
                      f"y con tabla `(VENTAS)` están {con_tabla}")
                return 1
            if len(empleados) <= len(vendedores):
                print("  FALLA: el tracker debería ofrecer a más gente que la "
                      "tabla de ventas")
                return 1
        finally:
            navegador.close()

    print("\nCapturas escritas en verification/modal_ventas_*.png")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1] if len(sys.argv) > 1 else "http://localhost:8000"))
