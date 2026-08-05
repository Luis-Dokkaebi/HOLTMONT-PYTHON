"""Infraestructura compartida para las pruebas de extremo a extremo (Playwright).

Resuelve dos problemas que impedian ejecutar la suite completa:

1. **Servidor unico.** `index.html` solo se comporta como la SPA real cuando lo
   sirve FastAPI (necesita `api_service.js` y los endpoints `/api/legacy/...`).
   Aqui se levanta *un* servidor por sesion de pytest y se reutiliza; si ya hay
   uno escuchando en el puerto, no se arranca otro.

2. **Pruebas hermeticas.** `index.html` carga Vue, Bootstrap, FontAwesome, etc.
   desde CDNs publicas. Sin salida a Internet el navegador nunca monta la app y
   las pruebas fallan por una razon ajena al codigo. Este modulo intercepta las
   peticiones externas del navegador y las resuelve desde un cache en disco que
   se llena con el stack HTTP de Python (que si respeta el proxy/CA del entorno).
   Resultado: las pruebas se ejecutan igual con red o sin ella, y no dependen de
   la disponibilidad de terceros.

No altera el comportamiento de la aplicacion: `index.html` sigue apuntando a las
CDNs tal como se despliega en produccion.
"""

import hashlib
import json
import os
import pathlib
import socket
import subprocess
import sys
import time

import pytest

REPO_ROOT = pathlib.Path(__file__).resolve().parent.parent
CACHE_DIR = pathlib.Path(__file__).resolve().parent / ".cdn_cache"
HOST = "127.0.0.1"
PORT = int(os.environ.get("HOLTMONT_TEST_PORT", "8000"))
BASE_URL = f"http://localhost:{PORT}"

LOCAL_HOSTS = {"localhost", "127.0.0.1", "[::1]", "::1"}


# --------------------------------------------------------------------------- #
# 0. Ninguna prueba escribe en la base de produccion
# --------------------------------------------------------------------------- #
# Desde que el backend escribe de verdad en Supabase, una prueba que llame a un
# endpoint de guardado con `.env` presente inserta filas en la base real. Ya
# paso: una corrida de `test_backend_refactor.py` dejo una tarea, su renglon en
# `plan_semanal`, su folio en `work_orders` y una linea en `system_log`.
#
# Aqui se desconectan las credenciales para toda la sesion de pytest. Las
# pruebas que necesitan una base usan `MemoryEngine`, que reproduce el upsert
# que fusiona, el NOT NULL con su 23502 y la reversion de la transaccion.
#
# Para correr a proposito contra una base real (una verificacion manual, no la
# suite): HOLTMONT_TEST_ALLOW_DB=1. No lo pongas en CI.

@pytest.fixture(scope="session", autouse=True)
def _sin_base_de_produccion():
    if os.environ.get("HOLTMONT_TEST_ALLOW_DB", "").strip() in {"1", "true", "yes"}:
        yield
        return

    guardadas = {
        clave: os.environ.pop(clave, None)
        for clave in ("SUPABASE_URL", "SUPABASE_KEY", "DATABASE_URL")
    }
    os.environ["BACKEND_ENGINE"] = "memoria"
    try:
        yield
    finally:
        os.environ.pop("BACKEND_ENGINE", None)
        for clave, valor in guardadas.items():
            if valor is not None:
                os.environ[clave] = valor


# --------------------------------------------------------------------------- #
# 1. Servidor FastAPI compartido
# --------------------------------------------------------------------------- #

def _port_open(host: str, port: int) -> bool:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.settimeout(0.5)
        return sock.connect_ex((host, port)) == 0


@pytest.fixture(scope="session", autouse=True)
def live_server():
    """Garantiza que haya un FastAPI sirviendo el frontend en `PORT`."""
    if _port_open(HOST, PORT):
        # Servidor levantado por fuera (p. ej. `run_tests.sh`): se reutiliza.
        yield BASE_URL
        return

    proc = subprocess.Popen(
        [sys.executable, "api/main.py"],
        cwd=str(REPO_ROOT),
        env={**os.environ, "PYTHONPATH": str(REPO_ROOT), "PORT": str(PORT)},
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
    )

    deadline = time.time() + 60
    while time.time() < deadline:
        if proc.poll() is not None:
            salida = (proc.stdout.read() or b"").decode(errors="replace")
            raise RuntimeError(f"El servidor murio al arrancar:\n{salida}")
        if _port_open(HOST, PORT):
            break
        time.sleep(0.25)
    else:
        proc.terminate()
        raise RuntimeError(f"El servidor no respondio en {BASE_URL} tras 60s")

    try:
        yield BASE_URL
    finally:
        proc.terminate()
        try:
            proc.wait(timeout=15)
        except subprocess.TimeoutExpired:
            proc.kill()


# --------------------------------------------------------------------------- #
# 2. Cache de recursos externos (CDNs)
# --------------------------------------------------------------------------- #

def _cache_paths(url: str):
    digest = hashlib.sha256(url.encode("utf-8")).hexdigest()[:32]
    return CACHE_DIR / f"{digest}.body", CACHE_DIR / f"{digest}.meta.json"


def _fetch_external(url: str):
    """Devuelve (body, content_type) usando el stack HTTP de Python.

    A diferencia del navegador, `requests` si honra HTTPS_PROXY y el CA bundle
    del entorno, por lo que puede poblar el cache donde Chromium no llega.
    """
    body_path, meta_path = _cache_paths(url)
    if body_path.exists() and meta_path.exists():
        meta = json.loads(meta_path.read_text())
        return body_path.read_bytes(), meta.get("content_type", "")

    try:
        import requests

        resp = requests.get(url, timeout=90, headers={"User-Agent": "Mozilla/5.0"})
        if resp.status_code >= 400:
            return None, None
        body, content_type = resp.content, resp.headers.get("content-type", "")
    except Exception:
        return None, None

    CACHE_DIR.mkdir(parents=True, exist_ok=True)
    body_path.write_bytes(body)
    meta_path.write_text(json.dumps({"content_type": content_type, "url": url}))
    return body, content_type


def _handle_route(route):
    url = route.request.url
    try:
        host = url.split("://", 1)[1].split("/", 1)[0].split(":")[0]
    except IndexError:
        route.continue_()
        return

    if host in LOCAL_HOSTS:
        route.continue_()
        return

    body, content_type = _fetch_external(url)
    if body is None:
        # Recursos accesorios (imagenes de Drive, iframes, tipografias): se
        # descartan para que la pagina no quede esperando por ellos.
        route.abort()
        return

    route.fulfill(status=200, body=body,
                  headers={"content-type": content_type or "application/octet-stream",
                           "access-control-allow-origin": "*"})


def _navegador_disponible() -> bool:
    """Chromium instalado Y capaz de arrancar (no basta con el paquete pip)."""
    try:
        from playwright.sync_api import sync_playwright
    except ImportError:
        return False
    try:
        with sync_playwright() as p:
            p.chromium.launch(headless=True).close()
        return True
    except Exception:
        return False


def pytest_collection_modifyitems(config, items):
    """Las pruebas de UI se SALTAN si falta el navegador; nunca se dan por buenas.

    RESTRICCIONES_EXTREMAS.md R8: un fallo de infraestructura no es un fallo de
    codigo, y mezclarlos entrena al equipo a ignorar la suite entera. Esto no
    debilita ninguna puerta: en CI se instala Chromium
    (`playwright install chromium`) y estas pruebas corren de verdad, en serio
    y bloqueando. Aqui solo se saltan -- con motivo visible en el reporte --
    cuando el binario sencillamente no existe.

    Extiende el criterio que ya seguia `pytest_configure` mas abajo para el
    caso de Playwright sin instalar.
    """
    de_ui = [i for i in items if "sync_playwright" in getattr(i.module, "__dict__", {})]
    if not de_ui or _navegador_disponible():
        return
    saltar = pytest.mark.skip(
        reason="Chromium no disponible en este entorno: `playwright install chromium`"
    )
    for item in de_ui:
        item.add_marker(saltar)


def pytest_configure(config):
    """Instala el interceptor en cada pagina que abran las pruebas.

    Las pruebas llaman a `sync_playwright()` y `browser.new_page()` por su
    cuenta, asi que el enganche se hace sobre esos metodos en lugar de exponer
    un fixture que habria que cablear prueba por prueba.
    """
    try:
        from playwright.sync_api import Browser, BrowserContext
    except ImportError:
        return  # Sin Playwright instalado solo corren las pruebas estaticas.

    def _wrap(cls, nombre):
        original = getattr(cls, nombre)
        if getattr(original, "_holtmont_wrapped", False):
            return

        def envuelto(self, *args, **kwargs):
            page = original(self, *args, **kwargs)
            page.route("**/*", _handle_route)
            return page

        envuelto._holtmont_wrapped = True
        setattr(cls, nombre, envuelto)

    _wrap(Browser, "new_page")
    _wrap(BrowserContext, "new_page")
