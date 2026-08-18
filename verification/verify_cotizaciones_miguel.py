"""
Revela las capturas de la tabla de Cotizaciones de Miguel Gallardo.

Reporte del dueño (2026-08-18): al entrar con la cuenta `MIGUEL_GALLARDO` el
menú solo traía «Tracker» y «Agregar Actividad»; le faltaba la tabla de
Cotizaciones que sí tiene Sebastián Padilla.

Esto no es una prueba: la que bloquea vive en la suite
(`tests/test_rbac_config.py::test_miguel_gallardo_recibe_su_tabla_de_cotizaciones`
y el escenario Gherkin de `tests/features/asignacion_de_cotizaciones.feature`).
Aquí solo se revelan las fotos, entrando por el mismo camino que él: el
formulario de login, `/api/login` y `getSystemConfig(role, username)`. Nada de
inyectar estado en el componente — lo que se ve es lo que rinde el backend.

    BACKEND_ENGINE=memoria \\
    DEV_LOGIN_USERS='MIGUEL_GALLARDO:<clave>:STAFF_USER:Miguel Angel Gallardo Jaramillo,SEBASTIAN_PADILLA:<clave>:STAFF_USER:Erick Sebastian Padilla Carrillo' \\
    PYTHONPATH=. python3 api/main.py &
    DEMO_PASSWORD=<clave> python3 verification/verify_cotizaciones_miguel.py [URL]

La contraseña de la demostración la fija quien levanta el servidor y solo vive
en esas dos variables de entorno: este archivo no la trae escrita.

Sebastián Padilla entra al final a propósito: es la referencia que dio el dueño
y su tabla se fotografía junto a la de Miguel para poder compararlas. Las dos
salen vacías porque el motor `memoria` no trae cotizaciones; lo que la captura
demuestra es que el módulo existe y abre la hoja con sufijo `(VENTAS)`, no que
haya datos.
"""

from __future__ import annotations

import os
import pathlib
import sys

RAIZ = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(RAIZ))

from playwright.sync_api import sync_playwright  # noqa: E402

from tests import conftest  # noqa: E402

DESTINO = pathlib.Path(__file__).resolve().parent
CUENTA = "MIGUEL_GALLARDO"
MODULO = "Cotizaciones"
TABLA = "MIGUEL GALLARDO (VENTAS)"

# La referencia que dio el dueño: "como Sebastián Padilla".
REFERENCIA = "SEBASTIAN_PADILLA"
TABLA_REFERENCIA = "SEBASTIAN PADILLA (VENTAS)"


def _entrar(page, base_url: str, clave: str, cuenta: str) -> None:
    page.goto(base_url)
    page.wait_for_selector(".login-card", state="visible", timeout=20000)
    page.fill('.login-card input[placeholder="Usuario"]', cuenta)
    page.fill('.login-card input[placeholder="Contraseña..."]', clave)
    page.click(".login-card button.btn-outline-light")
    page.wait_for_selector(".app-wrapper", state="visible", timeout=20000)
    # El menú se pinta con lo que responde `getSystemConfig`; sin esta espera la
    # captura podría salir antes de que llegue la configuración.
    page.wait_for_selector(f".sidebar .nav-item:has-text('{MODULO}')", timeout=20000)


def _abrir_cotizaciones(page, nombre_archivo: str, tabla: str) -> bool:
    page.click(f".sidebar .nav-item:has-text('{MODULO}')")
    page.wait_for_selector("table.table-excel thead th", timeout=20000)
    page.wait_for_timeout(800)
    page.screenshot(path=str(DESTINO / nombre_archivo))

    texto = page.locator(".view-area").inner_text().upper()
    if tabla.upper() not in texto:
        print(f"  FALLA: la vista no dice «{tabla}»")
        return False
    print(f"  tabla abierta: {tabla}")
    return True


def main(base_url: str) -> int:
    clave = os.environ.get("DEMO_PASSWORD", "").strip()
    if not clave:
        print("Falta DEMO_PASSWORD: la misma contraseña que pusiste en "
              "DEV_LOGIN_USERS al levantar el servidor.")
        return 2

    # Sirve las CDNs desde el cache en disco: las capturas salen iguales con red
    # y sin ella (ver tests/conftest.py).
    conftest.pytest_configure(None)

    with sync_playwright() as p:
        navegador = p.chromium.launch(headless=True)
        page = navegador.new_page(viewport={"width": 1500, "height": 900})
        try:
            print(f"{CUENTA}:")
            _entrar(page, base_url, clave, CUENTA)
            page.wait_for_timeout(800)
            page.screenshot(path=str(DESTINO / "cotizaciones_miguel_01_dashboard.png"))

            etiquetas = [e.strip() for e in
                         page.locator(".sidebar .nav-item .nav-text").all_inner_texts()]
            print(f"  menú: {[e for e in etiquetas if e]}")
            if MODULO not in etiquetas:
                print(f"  FALLA: «{MODULO}» no está en el menú")
                return 1

            if not _abrir_cotizaciones(page, "cotizaciones_miguel_02_tabla.png", TABLA):
                return 1

            print(f"\n{REFERENCIA}:")
            _entrar(page, base_url, clave, REFERENCIA)
            if not _abrir_cotizaciones(page, "cotizaciones_miguel_03_referencia.png",
                                       TABLA_REFERENCIA):
                return 1
        finally:
            navegador.close()

    print("\nCapturas escritas en verification/cotizaciones_miguel_*.png")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1] if len(sys.argv) > 1 else "http://localhost:8000"))
