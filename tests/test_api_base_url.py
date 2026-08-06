"""
`api_service.js` debe resolver la URL de la API desde el origen de la página.

Por qué existe esta prueba: el adaptador fijaba `http://localhost:8000` a mano
cuando el host era `localhost` o `127.0.0.1`, ignorando el puerto real desde el
que se servía la página. Arrancar la aplicación en cualquier otro puerto dejaba
el login roto de una forma difícil de diagnosticar: el `fetch` salía hacia un
puerto donde no había nada, el navegador no registraba ninguna petición a
`/api/` y la pantalla solo decía «Connection Error: TypeError: Failed to fetch».

El origen de la página es siempre el de la API: `vercel.json` sirve
`index.html`, `api_service.js` y `api/main.py` bajo el mismo dominio, y en local
FastAPI publica los tres. No hay ningún despliegue donde diverjan.

La comprobación es de comportamiento, no de texto: se evalúa la definición real
con Node bajo tres orígenes distintos. Una prueba que solo buscara la cadena
`localhost:8000` pasaría con cualquier otra forma de fijar el puerto a mano.
"""

from __future__ import annotations

import json
import os
import re
import shutil
import subprocess

import pytest

RAIZ = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
ADAPTADOR = os.path.join(RAIZ, "api_service.js")

# (origen de la página, URL base que debe resultar)
ORIGENES = [
    ("http://localhost:8000", "http://localhost:8000"),
    ("http://127.0.0.1:8010", "http://127.0.0.1:8010"),
    ("https://holtmont.vercel.app", "https://holtmont.vercel.app"),
]


def _definicion_de_api_base_url() -> str:
    """El bloque que define `API_BASE_URL`, tal cual está en el archivo."""
    with open(ADAPTADOR, encoding="utf-8") as fh:
        fuente = fh.read()

    m = re.search(r"^const API_BASE_URL =.*?;", fuente, re.S | re.M)
    assert m, "no se encontró la definición de `API_BASE_URL` en api_service.js"
    return m.group(0)


@pytest.mark.skipif(shutil.which("node") is None, reason="node no está instalado")
@pytest.mark.parametrize(("origen", "esperada"), ORIGENES)
def test_la_url_base_sale_del_origen_de_la_pagina(origen: str, esperada: str) -> None:
    """
    Servida desde cualquier origen, la API base debe ser ese mismo origen.

    El caso de `127.0.0.1:8010` es el que fallaba: devolvía
    `http://localhost:8000` y el login moría sin llegar a hacer la petición.
    """
    hostname = origen.split("://", 1)[1].split(":")[0]
    guion = f"""
        const window = {{ location: {{
            origin: {json.dumps(origen)},
            hostname: {json.dumps(hostname)},
        }} }};
        {_definicion_de_api_base_url()}
        console.log(API_BASE_URL);
    """

    salida = subprocess.run(
        ["node", "-e", guion], capture_output=True, text=True, timeout=30, check=False)

    assert salida.returncode == 0, f"node falló: {salida.stderr}"
    assert salida.stdout.strip() == esperada


def test_la_url_base_no_fija_ningun_puerto_a_mano() -> None:
    """
    Ninguna forma de escribir un puerto literal en la definición.

    Complementa la prueba de comportamiento: cubre el caso de que alguien vuelva
    a introducir un puerto para un origen que estas tres muestras no cubren.
    """
    definicion = _definicion_de_api_base_url()

    puertos = re.findall(r":\d{2,5}\b", definicion)
    assert not puertos, (
        f"`API_BASE_URL` fija el/los puerto(s) {puertos} a mano; "
        "debe salir de `window.location.origin`"
    )
