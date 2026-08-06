"""
Qué columnas llevan selector de fecha en la vista.

`index.html` decide por el **nombre del encabezado** si una celda se renderiza
como `<input type="date">` o como texto. Eso acopla `TASK_HEADER_MAP` con el
render: cambiar el nombre de una columna puede ponerle un calendario a una
columna de texto, o quitárselo a una fecha.

El defecto que cubre: la condición incluía `.includes('ALTA')`, y `ALTA` es el
**área** —así se rotula la columna en la vista del original—. Esa columna de
texto se renderizaba como calendario y no se podía escribir. Ninguna columna de
fecha dependía de ese término: todas contienen `FECHA` (`FECHA ALTA`,
`FECHA DE ALTA`, `FECHA_ALTA`), así que quitarlo no le quita el calendario a
ninguna. Las que solo casaban por `ALTA` eran justo las dos que no deben
tenerlo: el área y `HORA_ALTA`, que es una hora.

Se evalúa la condición real con Node sobre los encabezados que la API rinde: una
prueba de texto no detectaría el acoplamiento.
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

# Encabezados que la API rinde y que SÍ son fechas: llevan calendario.
CON_CALENDARIO = ["FECHA", "FECHA_ESTIMADA_FIN", "FECHA_RESPUESTA",
                  "F. VISITA", "F. INICIO", "F. ENTREGA"]

# Encabezados que NO son fechas: si les sale calendario, no se pueden escribir.
SIN_CALENDARIO = ["FOLIO", "ALTA", "AREA", "HORA", "HR. EST. FIN", "CONCEPTO", "CLASIFICACION", "INVOLUCRADOS",
                  "AVANCE %", "RELOJ", "RESTRICCIONES", "PRIORIDADES", "RIESGOS",
                  "CORREO", "CARPETA", "STATUS", "CLIENTE", "REQUISITOR"]


def _condicion() -> str:
    """La condición `v-else-if` que decide si la celda es un date-picker."""
    with open(INDEX, encoding="utf-8") as fh:
        fuente = fh.read()

    m = re.search(
        r'v-else-if="(String\(h\)\.toUpperCase\(\)\.includes\(\'FECHA\'\)[^"]*?)"',
        fuente)
    assert m, "no se encontró la condición del selector de fecha en index.html"
    return m.group(1)


def _evaluar(encabezados: list) -> dict:
    guion = f"""
        const cond = (h) => ({_condicion()});
        const hs = {json.dumps(encabezados)};
        console.log(JSON.stringify(Object.fromEntries(hs.map(h => [h, !!cond(h)]))));
    """
    salida = subprocess.run(["node", "-e", guion], capture_output=True,
                            text=True, timeout=30, check=False)
    assert salida.returncode == 0, f"node falló: {salida.stderr}"
    return json.loads(salida.stdout)


@pytest.mark.skipif(shutil.which("node") is None, reason="node no está instalado")
@pytest.mark.parametrize("encabezado", CON_CALENDARIO)
def test_las_columnas_de_fecha_llevan_calendario(encabezado: str) -> None:
    assert _evaluar([encabezado])[encabezado] is True, (
        f"{encabezado} es una fecha y debe abrir el selector de calendario"
    )


@pytest.mark.skipif(shutil.which("node") is None, reason="node no está instalado")
@pytest.mark.parametrize("encabezado", SIN_CALENDARIO)
def test_las_columnas_de_texto_no_llevan_calendario(encabezado: str) -> None:
    assert _evaluar([encabezado])[encabezado] is False, (
        f"{encabezado} no es una fecha; con calendario no se puede escribir su valor"
    )


@pytest.mark.skipif(shutil.which("node") is None, reason="node no está instalado")
def test_ningun_encabezado_que_hoy_rinde_la_api_recibe_un_calendario_indebido() -> None:
    """
    El control de conjunto sobre los mapas reales.

    Es el que detecta el acoplamiento sin que nadie lo busque: si un encabezado
    nuevo cae en la condición por casualidad —lleva `FECHA` o `F. INICIO`
    dentro—, aquí se ve.
    """
    from api.services.sheets import QUOTE_HEADER_MAP, TASK_HEADER_MAP

    fechas = {"FECHA", "FECHA_ESTIMADA_FIN", "FECHA_RESPUESTA",
              "F. VISITA", "F. INICIO", "F. ENTREGA"}
    encabezados = [h for h, _ in TASK_HEADER_MAP] + [h for h, _ in QUOTE_HEADER_MAP]

    resultado = _evaluar(encabezados)
    indebidos = [h for h, tiene in resultado.items() if tiene and h not in fechas]

    assert indebidos == [], (
        f"estas columnas no son fechas y abren el calendario: {indebidos}"
    )
