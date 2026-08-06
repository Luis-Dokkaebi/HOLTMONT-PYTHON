"""
Columnas que la vista de trackers y cotizaciones no muestra.

`index.html` declara la lista en `COLUMNAS_OCULTAS` y `visibleTrackerHeaders`
la aplica sobre los encabezados que devuelve la API. La API expone **toda**
columna presente en la tabla (`sheets.build_header_map`), que es lo correcto
para no perder datos nuevos; decidir cuáles se enseñan es cosa de la vista.

Qué se oculta y por qué:

  * `PROCESO_LOG`, `PROCESO`, `MAP COT` — alimentan el widget de Papa Caliente
    que se dibuja *dentro* de la columna ESTATUS. Enseñarlas además como
    columnas propias mostraría el JSON crudo. El original hace lo mismo.
  * `MONTO` — no aparece en la vista de cotizaciones del original y está vacía
    en las 661 filas de las 7 hojas de ventas. Era una columna en blanco.
  * Las columnas técnicas (`sheets.COLUMNAS_TECNICAS`) — `ID`, `DEDUPE_KEY`,
    `FOLIO_SINTETICO`, `ASSIGNEE_ID`, `VENDEDOR_ID`, `SOURCE_SHEET`,
    `CREATED_AT`. Son claves y metadatos del esquema relacional que el original
    no tiene; al usuario le llegaban seis columnas de UUID y marcas de tiempo al
    final de cada tabla. `ID` era además engañosa: en las hojas de Apps Script
    `ID` es el folio, y aquí es la clave primaria de Postgres.

Ocultarlas no afecta a la escritura: el filtro solo gobierna el render, y la
fila conserva todas sus claves (`isFieldEditable` sigue leyendo `row['ID']`).

La comprobación es de comportamiento: se evalúa el filtro real con Node sobre
una lista de encabezados. Una prueba que solo buscara la cadena `'MONTO'` en el
archivo pasaría aunque el filtro estuviera roto.
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

TECNICAS = ["ID", "DEDUPE_KEY", "FOLIO_SINTETICO", "ASSIGNEE_ID", "VENDEDOR_ID",
            "SOURCE_SHEET", "CREATED_AT"]

OCULTAS = ["PROCESO_LOG", "PROCESO", "MAP COT", "MONTO"] + TECNICAS

# Las 20 que se ven en la hoja de cotizaciones de Apps Script. Ninguna se oculta.
VISIBLES = [
    "FOLIO", "AREA", "CLIENTE", "CONCEPTO", "CLASIFICACION", "VENDEDOR",
    "F. VISITA", "F. INICIO", "F. ENTREGA", "DIAS", "AVANCE", "ESTATUS",
    "COMENTARIOS", "REQUISITOR", "PRIO. COT.", "INFO CLIENTE", "F2",
    "COTIZACION", "TIMELINE", "LAYOUT",
]


def _fuente() -> str:
    with open(INDEX, encoding="utf-8") as fh:
        return fh.read()


def _declaracion_de_ocultas() -> str:
    m = re.search(r"const COLUMNAS_OCULTAS = \[[^\]]*\];", _fuente())
    assert m, "no se encontró `const COLUMNAS_OCULTAS = [...]` en index.html"
    return m.group(0)


def _filtro() -> str:
    """El cuerpo del `.filter(...)` que aplica `visibleTrackerHeaders`."""
    m = re.search(r"return staffTracker\.value\.headers\.filter\((.*?)\);",
                  _fuente(), re.S)
    assert m, "no se encontró el filtro de `visibleTrackerHeaders`"
    return m.group(1)


@pytest.mark.skipif(shutil.which("node") is None, reason="node no está instalado")
def test_el_filtro_oculta_exactamente_las_columnas_declaradas() -> None:
    """Sobre la lista real de encabezados, se van las 4 y se quedan las 20."""
    entrada = VISIBLES + OCULTAS + ["ESTATUS_2", "SOURCE_SHEET"]
    guion = f"""
        {_declaracion_de_ocultas()}
        const headers = {json.dumps(entrada)};
        console.log(JSON.stringify(headers.filter({_filtro()})));
    """

    salida = subprocess.run(["node", "-e", guion], capture_output=True,
                            text=True, timeout=30, check=False)
    assert salida.returncode == 0, f"node falló: {salida.stderr}"

    visibles = json.loads(salida.stdout)

    for col in OCULTAS:
        assert col not in visibles, f"{col} debería ocultarse y se está mostrando"
    for col in VISIBLES:
        assert col in visibles, f"{col} es una columna real de la hoja y se ocultó"


@pytest.mark.skipif(shutil.which("node") is None, reason="node no está instalado")
def test_el_filtro_no_distingue_mayusculas_ni_espacios() -> None:
    """
    La API rinde `MONTO`, pero una hoja podría traer `monto` o ` Monto `.

    El filtro normaliza con `.toUpperCase().trim()`; si alguien lo quita, una
    columna oculta reaparece según cómo venga escrita.
    """
    guion = f"""
        {_declaracion_de_ocultas()}
        const headers = ["monto", " Monto ", "MONTO", "proceso"];
        console.log(JSON.stringify(headers.filter({_filtro()})));
    """

    salida = subprocess.run(["node", "-e", guion], capture_output=True,
                            text=True, timeout=30, check=False)
    assert salida.returncode == 0, f"node falló: {salida.stderr}"
    assert json.loads(salida.stdout) == []


def test_monto_esta_declarada_como_oculta() -> None:
    """Deja constancia de la decisión: no se muestra en ninguna hoja de ventas."""
    assert "'MONTO'" in _declaracion_de_ocultas()


def test_las_columnas_tecnicas_del_esquema_no_se_muestran():
    """
    La lista de la vista cubre las que `sheets.COLUMNAS_TECNICAS` clasifica así.

    Se contrasta contra el backend en vez de repetir la lista a mano: si mañana
    se añade una columna técnica allí, esta prueba avisa de que la vista aún la
    enseña, en lugar de que aparezca un UUID en la tabla de alguien.
    """
    from api.services.sheets import COLUMNAS_TECNICAS

    declaradas = {c.upper() for c in COLUMNAS_TECNICAS}
    ocultas = {c.upper() for c in re.findall(r"'([^']+)'", _declaracion_de_ocultas())}

    assert declaradas - ocultas == set(), (
        f"columnas técnicas que la vista sigue mostrando: {sorted(declaradas - ocultas)}"
    )
