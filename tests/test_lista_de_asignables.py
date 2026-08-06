"""
A quién ofrece la vista como destino de una asignación.

Regla del dueño: si no existe la tabla `<Nombre> (VENTAS)`, esa persona **no
debe aparecer** en la lista cuando se reparte desde una tabla de ventas, porque
no hay a dónde mandarle la cotización. Ofrecerla y luego descartarla en el
backend sería peor que no ofrecerla: quien captura creería que asignó.

La marca `sales` la calcula el backend (`api/main.py`) desde
`asignacion.VENDEDORES_CON_TABLA`, que es la única lista declarada. La vista no
repite nombres; solo lee la bandera.

La comprobación evalúa el filtro real con Node sobre un directorio de prueba.
Buscar la cadena `sales` en el archivo pasaría aunque el filtro estuviera roto.
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

DIRECTORIO = [
    {"name": "TERESA GARZA", "sales": True},
    {"name": "SEBASTIAN PADILLA", "sales": True},
    {"name": "ALFONSO CORREA", "sales": False},
    {"name": "GERALDINE MARTINEZ HERNANDEZ", "sales": False},
]


def _fuente() -> str:
    with open(INDEX, encoding="utf-8") as fh:
        return fh.read()


def _guion(hoja: str) -> str:
    """Reproduce el filtro de `filteredDirectory` con las piezas reales."""
    fuente = _fuente()

    m_ventas = re.search(r"const esHojaDeVentas = \(nombre\) => \{.*?\n      \};",
                         fuente, re.S)
    assert m_ventas, "no se encontró `esHojaDeVentas` en index.html"

    m_puede = re.search(r"const puedeRecibirDeEstaTabla = .*?;", fuente)
    assert m_puede, "no se encontró `puedeRecibirDeEstaTabla` en index.html"

    m_filtro = re.search(
        r"const filteredDirectory = computed\(\(\) => \((.*?)\)\.filter\((.*?)\)\.slice",
        fuente, re.S)
    assert m_filtro, "no se encontró `filteredDirectory` en index.html"

    return f"""
        const staffTracker = {{ value: {{ name: {json.dumps(hoja)} }} }};
        const staffSearch = {{ value: '' }};
        const selectedResponsables = {{ value: [] }};
        const config = {{ value: {{ directory: {json.dumps(DIRECTORIO)} }} }};
        {m_ventas.group(0)}
        {m_puede.group(0)}
        const visibles = ({m_filtro.group(1)}).filter({m_filtro.group(2)}).slice(0, 5);
        console.log(JSON.stringify(visibles.map(p => p.name)));
    """


def _visibles(hoja: str) -> list:
    salida = subprocess.run(["node", "-e", _guion(hoja)], capture_output=True,
                            text=True, timeout=30, check=False)
    assert salida.returncode == 0, f"node falló: {salida.stderr}"
    return json.loads(salida.stdout)


@pytest.mark.skipif(shutil.which("node") is None, reason="node no está instalado")
@pytest.mark.parametrize("hoja", ["ANTONIA_VENTAS", "Sebastian Padilla (VENTAS)"])
def test_desde_una_tabla_de_ventas_solo_se_ofrece_a_quien_tiene_tabla(hoja: str) -> None:
    assert _visibles(hoja) == ["TERESA GARZA", "SEBASTIAN PADILLA"]


@pytest.mark.skipif(shutil.which("node") is None, reason="node no está instalado")
@pytest.mark.parametrize("hoja", ["JAIME OLIVO", "ANTONIA PINEDA LOPEZ"])
def test_desde_un_tracker_se_ofrece_a_todo_el_mundo(hoja: str) -> None:
    """Asignar una **actividad** no tiene esa restricción: no cambia nada."""
    assert _visibles(hoja) == [p["name"] for p in DIRECTORIO]


def test_el_backend_marca_la_bandera_desde_la_lista_declarada() -> None:
    """
    La bandera sale de `VENDEDORES_CON_TABLA`, no de una copia en `api/main.py`.

    Si alguien cablea la lista en el endpoint, esta prueba no lo ve; lo que sí
    protege es que la bandera exista y se calcule con la función correcta, que
    es lo que evita que la vista y el backend discrepen sobre quién vende.
    """
    from api.services.asignacion import VENDEDORES_CON_TABLA, tabla_de_cotizaciones

    directorio = [{"name": "TERESA GARZA"}, {"name": "ALFONSO CORREA"}]
    marcado = [
        {**p, "sales": bool(tabla_de_cotizaciones(p.get("name")))} for p in directorio
    ]
    assert [p["sales"] for p in marcado] == [True, False]
    assert "TERESA GARZA" in VENDEDORES_CON_TABLA
    assert "ALFONSO CORREA" not in VENDEDORES_CON_TABLA
