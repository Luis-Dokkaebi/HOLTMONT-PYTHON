"""
Etiquetas de las columnas en la vista (`getHeaderLabel` de `index.html`).

La API rinde el nombre crudo de la columna en mayúsculas
(`sheets._nombre_visible`): `FECHA_ESTIMADA_FIN`, `HORA_ESTIMADA_FIN`. La vista
las rotula como el original —`Fec. Est. Fin`, `Hr. Est. Fin`— y para eso
`getHeaderLabel` traía una lista de comparaciones exactas.

El defecto que cubre esta prueba: esas comparaciones esperaban la forma **con
espacios** (`'FECHA ESTIMADA DE FIN'`), que es como se llama la columna en la
hoja de Apps Script, mientras que la API entrega la forma **con guiones bajos**.
Ninguna casaba, así que las dos columnas caían al rotulador genérico y salían
como `Fecha_estimada_fin` y `Hora_estimada_fin` — con guion bajo a la vista del
usuario y sin parecerse al original.

Se comprueba evaluando el `getHeaderLabel` real con Node: una prueba de texto
sobre el archivo pasaría aunque la comparación siguiera sin casar.
"""

from __future__ import annotations

import json
import os
import re
import shutil
import subprocess

import pytest

RAIZ = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
INDEX = os.path.join(RAIZ, "index.html")

# (encabezado tal como lo rinde la API, etiqueta que debe verse)
ETIQUETAS_ESPERADAS = [
    ("CLASIFICACION", "Clasi"),
    ("RESTRICCIONES", "Restricciones y Comentarios"),
    # Las dos formas: la que entrega la API y la que usa la hoja de Apps Script.
    ("FECHA_ESTIMADA_FIN", "Fec. Est. Fin"),
    ("FECHA ESTIMADA DE FIN", "Fec. Est. Fin"),
    ("HORA_ESTIMADA_FIN", "Hr. Est. Fin"),
    ("HORA ESTIMADA DE FIN", "Hr. Est. Fin"),
    # Sin regla propia: se capitaliza y ya.
    ("CONCEPTO", "Concepto"),
    ("RIESGOS", "Riesgos"),
]


def _fuente() -> str:
    with open(INDEX, encoding="utf-8") as fh:
        return fh.read()


def _bloque_de_etiquetas() -> str:
    """`getHeaderLabel` y lo que necesite para evaluarse fuera de Vue."""
    fuente = _fuente()

    m = re.search(r"const getHeaderLabel = \(h\) => \{.*?\n      \};", fuente, re.S)
    assert m, "no se encontró `getHeaderLabel` en index.html"
    funcion = m.group(0)

    # `getHeaderLabel` consulta `currentUsername` para el caso de ANTONIA_VENTAS.
    previo = "const currentUsername = { value: '' };\n"

    normalizador = re.search(r"const claveEtiqueta = .*?;\n", fuente, re.S)
    if normalizador:
        previo += normalizador.group(0)

    tabla = re.search(r"const ETIQUETAS_DE_COLUMNA = \{.*?\n      \};", fuente, re.S)
    if tabla:
        previo += tabla.group(0) + "\n"

    return previo + funcion


@pytest.mark.skipif(shutil.which("node") is None, reason="node no está instalado")
@pytest.mark.parametrize(("encabezado", "etiqueta"), ETIQUETAS_ESPERADAS)
def test_la_columna_se_rotula_como_en_el_original(encabezado: str, etiqueta: str) -> None:
    guion = f"""
        {_bloque_de_etiquetas()}
        console.log(JSON.stringify(getHeaderLabel({json.dumps(encabezado)})));
    """

    salida = subprocess.run(["node", "-e", guion], capture_output=True,
                            text=True, timeout=30, check=False)
    assert salida.returncode == 0, f"node falló: {salida.stderr}"

    obtenida = json.loads(salida.stdout)
    assert obtenida == etiqueta, (
        f"la columna {encabezado!r} se rotula {obtenida!r} y debería verse {etiqueta!r}"
    )


@pytest.mark.skipif(shutil.which("node") is None, reason="node no está instalado")
def test_ninguna_etiqueta_visible_conserva_guiones_bajos() -> None:
    """
    El guion bajo delata una columna sin rotular: es un nombre de base de datos.

    Se recorren los encabezados que la API rinde de verdad para el tracker.
    """
    from api.services.sheets import QUOTE_HEADER_MAP, TASK_HEADER_MAP

    # Se derivan de los mapas en vez de copiarlos: si mañana se añade una
    # columna curada, esta prueba la cubre sola. Se descuentan las que la vista
    # oculta (`PROCESO_LOG` y compañía): su etiqueta no llega a nadie, así que
    # exigirle rótulo sería inventar un requisito.
    m = re.search(r"const COLUMNAS_OCULTAS = \[([^\]]*)\];", _fuente())
    assert m, "no se encontró `COLUMNAS_OCULTAS` en index.html"
    ocultas = {c.upper() for c in re.findall(r"'([^']+)'", m.group(1))}

    encabezados = [h for h, _ in TASK_HEADER_MAP] + [h for h, _ in QUOTE_HEADER_MAP]
    encabezados = [h for h in encabezados if h.upper() not in ocultas]
    guion = f"""
        {_bloque_de_etiquetas()}
        const hs = {json.dumps(encabezados)};
        console.log(JSON.stringify(hs.map(getHeaderLabel)));
    """

    salida = subprocess.run(["node", "-e", guion], capture_output=True,
                            text=True, timeout=30, check=False)
    assert salida.returncode == 0, f"node falló: {salida.stderr}"

    con_guion = [e for e in json.loads(salida.stdout) if "_" in e]
    assert con_guion == [], f"estas etiquetas llegan sin rotular al usuario: {con_guion}"
