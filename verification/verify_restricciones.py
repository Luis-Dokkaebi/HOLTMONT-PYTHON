"""
Regenera las capturas de «Restricciones y Comentarios» del tracker de ventas.

Las imágenes `restricciones_*.png` de esta carpeta son la evidencia visual de
que la celda se deja escribir y guardar con la actividad ya asignada. Este
guion es lo que las produce, para que cualquiera pueda rehacerlas en vez de
tener que creerse las que están subidas.

La comprobación que bloquea vive en `tests/test_restricciones_ui.py` y corre en
la suite; esto es solo el revelado de las fotos.

    python3 verification/verify_restricciones.py [URL]

`URL` por defecto es http://localhost:8000 (el servidor que levanta
`run_tests.sh`). Levántalo antes:

    BACKEND_ENGINE=memoria PYTHONPATH=. python3 api/main.py
"""

from __future__ import annotations

import pathlib
import sys

RAIZ = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(RAIZ))

from playwright.sync_api import sync_playwright  # noqa: E402

from tests import conftest  # noqa: E402
from tests.test_restricciones_ui import (  # noqa: E402
    FILA,
    INYECTAR_TRACKER,
    TEXTO,
    _encabezados_de_la_api,
)

DESTINO = pathlib.Path(__file__).resolve().parent


def main(base_url: str) -> int:
    # Sirve las CDNs desde el cache en disco: las capturas salen iguales con red
    # y sin ella (ver tests/conftest.py).
    conftest.pytest_configure(None)

    with sync_playwright() as p:
        navegador = p.chromium.launch(headless=True)
        page = navegador.new_page(viewport={"width": 1500, "height": 900})
        try:
            page.goto(base_url)
            page.wait_for_selector(".login-card", state="visible", timeout=20000)
            page.evaluate(INYECTAR_TRACKER,
                          {"headers": _encabezados_de_la_api(),
                           "rows": [dict(FILA)]})
            page.wait_for_selector("table.table-excel tbody tr", timeout=15000)
            page.wait_for_timeout(600)

            rotulos = page.locator("table.table-excel thead th").all_inner_texts()
            indice = next(i for i, t in enumerate(rotulos) if "Restricciones" in t)
            celda = page.locator(
                f"table.table-excel tbody tr:first-child "
                f"td:nth-child({indice + 1}) textarea")

            solo_lectura = celda.evaluate("el => el.readOnly")
            print(f"readOnly = {solo_lectura}")
            page.screenshot(path=str(DESTINO / "restricciones_01_tabla.png"))

            celda.click()
            celda.type(TEXTO, delay=12)
            page.wait_for_timeout(300)
            page.screenshot(path=str(DESTINO / "restricciones_02_escribiendo.png"))

            with page.expect_response(
                lambda r: "/api/legacy/updateTask" in r.url, timeout=20000
            ) as espera:
                page.click("table.table-excel tbody tr:first-child "
                           "td:last-child button")
            respuesta = espera.value
            print(f"POST {respuesta.status} -> "
                  f"{respuesta.json().get('data', {}).get('RESTRICCIONES')!r}")

            page.wait_for_timeout(1200)
            page.screenshot(path=str(DESTINO / "restricciones_03_guardado.png"))
        finally:
            navegador.close()

    print(f"Capturas escritas en {DESTINO}")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1] if len(sys.argv) > 1 else "http://localhost:8000"))
