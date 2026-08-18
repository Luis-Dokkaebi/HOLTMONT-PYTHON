"""
A quién ofrece la vista como destino de una asignación.

Regla del dueño: si no existe la tabla `<Nombre> (VENTAS)`, esa persona **no
debe aparecer** en la lista cuando se reparte desde una tabla de ventas, porque
no hay a dónde mandarle la cotización. Ofrecerla y luego descartarla en el
backend sería peor que no ofrecerla: quien captura creería que asignó.

La marca `sales` la calcula el backend (`api/main.py`) desde
`asignacion.VENDEDORES_CON_TABLA`, que es la única lista declarada. La vista no
repite nombres; solo lee la bandera.

**Hay dos entradas a la misma decisión y las dos se comprueban aquí.** El
`filteredDirectory` de los chips es una; el modal de la columna VENDEDOR —el que
de verdad usa Toñita, `openVendorSelector`— es la otra, y hasta el 2026-08-18
ofrecía el directorio entero (`allStaffList`) porque la regla del 2026-08-06
solo se había aplicado a la primera. Elegir ahí a alguien sin tabla `(VENTAS)`
guardaba la fila sin error y sin copia: `destinos_espejo` no tiene a dónde
mandarla.

La comprobación evalúa los filtros reales con Node sobre un directorio de
prueba. Buscar la cadena `sales` en el archivo pasaría aunque el filtro
estuviera roto.
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


def _guion_del_modal(hoja: str) -> str:
    """
    Reproduce la lista que arma `openVendorSelector`, la del modal.

    Se toma **la línea del propio modal** (`const staffToUse = ...`), no la
    función que se supone que debe usar: si mañana alguien la vuelve a cablear a
    `allStaffList`, esto lo ve. Por eso `allStaffList` también se define en el
    guion, con el directorio entero — si el modal la usa, la lista sale con
    todos y la prueba falla.
    """
    fuente = _fuente()

    m_ventas = re.search(r"const esHojaDeVentas = \(nombre\) => \{.*?\n      \};",
                         fuente, re.S)
    assert m_ventas, "no se encontró `esHojaDeVentas` en index.html"

    m_puede = re.search(r"const puedeRecibirDeEstaTabla = .*?;", fuente)
    assert m_puede, "no se encontró `puedeRecibirDeEstaTabla` en index.html"

    m_asignables = re.search(
        r"const asignablesDeEstaTabla = \(\) => .*?\.filter\(\(n, i, a\) => a\.indexOf\(n\) === i\);",
        fuente, re.S)
    assert m_asignables, "no se encontró `asignablesDeEstaTabla` en index.html"

    m_modal = re.search(
        r"const openVendorSelector = .*?\n( +)const staffToUse = (.*?);", fuente, re.S)
    assert m_modal, "no se encontró `staffToUse` dentro de `openVendorSelector`"

    return f"""
        const staffTracker = {{ value: {{ name: {json.dumps(hoja)} }} }};
        const currentUsername = {{ value: 'ANTONIA_VENTAS' }};
        const config = {{ value: {{ directory: {json.dumps(DIRECTORIO)} }} }};
        const allStaffList = {{ value: config.value.directory.map(p => p.name) }};
        {m_ventas.group(0)}
        {m_puede.group(0)}
        {m_asignables.group(0)}
        const staffToUse = {m_modal.group(2)};
        console.log(JSON.stringify(staffToUse));
    """


def _del_modal(hoja: str) -> list:
    salida = subprocess.run(["node", "-e", _guion_del_modal(hoja)],
                            capture_output=True, text=True, timeout=30, check=False)
    assert salida.returncode == 0, f"node falló: {salida.stderr}"
    return json.loads(salida.stdout)


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


# ---------------------------------------------------------------------------
# El modal de la columna VENDEDOR / RESPONSABLE / INVOLUCRADOS
# ---------------------------------------------------------------------------
#
# Es el que se ve en la captura del reporte (2026-08-18): Toñita pulsa la celda
# y sale «Asignar Vendedor / Empleado» con casillas. Ofrecía a los 40 del
# directorio.

@pytest.mark.skipif(shutil.which("node") is None, reason="node no está instalado")
@pytest.mark.parametrize("hoja", ["ANTONIA_VENTAS", "Sebastian Padilla (VENTAS)"])
def test_el_modal_de_una_tabla_de_ventas_solo_ofrece_a_quien_tiene_tabla(hoja: str) -> None:
    assert _del_modal(hoja) == ["TERESA GARZA", "SEBASTIAN PADILLA"]


@pytest.mark.skipif(shutil.which("node") is None, reason="node no está instalado")
@pytest.mark.parametrize("hoja", ["JAIME OLIVO", "ANTONIA PINEDA LOPEZ"])
def test_el_modal_de_un_tracker_sigue_ofreciendo_a_todo_el_mundo(hoja: str) -> None:
    """
    La diferencia que pidió el dueño: en el tracker se asigna una **actividad** y
    todo el mundo tiene tracker, así que ahí no se filtra a nadie. `ANTONIA
    PINEDA LOPEZ` es el caso fino: es su tracker personal, no su tabla de ventas.
    """
    assert _del_modal(hoja) == [p["name"] for p in DIRECTORIO]


@pytest.mark.skipif(shutil.which("node") is None, reason="node no está instalado")
@pytest.mark.parametrize("hoja", ["ANTONIA_VENTAS", "JAIME OLIVO"])
def test_las_dos_entradas_ofrecen_lo_mismo(hoja: str) -> None:
    """
    Chips y modal son dos puertas a la misma decisión.

    Que discreparan es lo que se reportó: la regla del 2026-08-06 se aplicó a
    `filteredDirectory` y no a `openVendorSelector`. Esta prueba falla si mañana
    alguien vuelve a arreglar solo una de las dos.
    """
    assert _del_modal(hoja) == _visibles(hoja)


def test_el_modal_no_ofrece_la_tabla_maestra_como_persona() -> None:
    """`ANTONIA_VENTAS` es una tabla, no alguien a quien asignarle algo."""
    fuente = _fuente()
    assert "p.name !== 'ANTONIA_VENTAS' && puedeRecibirDeEstaTabla(p)" in fuente


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
