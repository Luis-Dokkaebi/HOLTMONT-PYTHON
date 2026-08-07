"""
El panorama del tracker: cuatro indicadores derivados de las reglas existentes.

Rediseño pedido por el cliente (2026-08-07): que la tabla no se vea plana y que
arriba se muestre el panorama de actividades. Es un cambio **visual**: las
columnas, el semáforo y las funciones de guardado no se tocan.

La decisión que importa está en de dónde salen los números:

  * **Retrasada** es, literalmente, la fila que el semáforo pinta de rojo. El
    dueño lo definió como "una actividad A que lleva +3 días está atrasada", y
    eso ya es `getTrafficStyle`: A > 3, AA > 15, AAA > 30. Se reusa la función
    en vez de recalcular los umbrales, para que no existan dos verdades: si un
    umbral cambia, el panel cambia con él.
  * **Terminada** es lo que ya está en TAREAS REALIZADAS (`history`), que lo
    decide el backend con `_esta_archivada`.
  * **Urgente** sale de la columna PRIORIDAD.
  * **Total** es activas + terminadas.

La dona muestra solo tres grupos —terminadas, retrasadas y en tiempo— porque son
los únicos que no se solapan y suman el total. Urgentes se queda fuera a
propósito: una urgente puede estar además retrasada, y la suma dejaría de
cuadrar sin que nadie lo note.
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


def _fuente() -> str:
    with open(INDEX, encoding="utf-8") as fh:
        return fh.read()


def _bloque(patron: str, nombre: str) -> str:
    m = re.search(patron, _fuente(), re.S)
    assert m, f"no se encontró {nombre} en index.html"
    return m.group(0)


def _node(guion: str):
    salida = subprocess.run(["node", "-e", guion], capture_output=True,
                            text=True, timeout=30, check=False)
    assert salida.returncode == 0, f"node falló: {salida.stderr}"
    return json.loads(salida.stdout)


def _entorno() -> str:
    """Las funciones reales de la vista, listas para evaluar con Node."""
    return "\n".join([
        _bloque(r"const getTrafficStyle = \(row\) => \{.*?\n      \};", "getTrafficStyle"),
        _bloque(r"const CLASIFICACIONES = .*?;", "CLASIFICACIONES"),
        _bloque(r"const valorDeColumna = .*?\n      \};", "valorDeColumna"),
        _bloque(r"const clasificacionDe = .*?;", "clasificacionDe"),
        _bloque(r"const esUrgente = .*?;", "esUrgente"),
        _bloque(r"const esRetrasada = .*?;", "esRetrasada"),
        _bloque(r"const desglosar = \(filas\) => \{.*?\n      \};", "desglosar"),
    ])


# ---------------------------------------------------------------------------
# Retrasada = la que el semáforo pinta de rojo
# ---------------------------------------------------------------------------

@pytest.mark.skipif(shutil.which("node") is None, reason="node no está instalado")
@pytest.mark.parametrize(("clasi", "dias", "retrasada"), [
    # El ejemplo literal del dueño: una A con más de 3 días.
    ("A", 3, False), ("A", 4, True), ("A", 40, True),
    ("AA", 15, False), ("AA", 16, True),
    ("AAA", 30, False), ("AAA", 31, True),
    # Sin clasificación no hay plazo contra el que llegar tarde.
    ("", 999, False), ("B", 999, False),
])
def test_retrasada_es_exactamente_el_rojo_del_semaforo(clasi, dias, retrasada) -> None:
    guion = f"""
        {_entorno()}
        console.log(JSON.stringify(esRetrasada(
            {{ CLASIFICACION: {json.dumps(clasi)}, RELOJ: {dias} }})));
    """
    assert _node(guion) is retrasada


@pytest.mark.skipif(shutil.which("node") is None, reason="node no está instalado")
def test_el_panel_no_define_umbrales_propios() -> None:
    """
    `esRetrasada` tiene que consultar `getTrafficStyle`, no repetir los números.

    Si alguien copiara los umbrales aquí, cambiar el semáforo dejaría el panel
    contando mal y en silencio.
    """
    m = re.search(r"const esRetrasada = .*?;", _fuente())
    assert m and "getTrafficStyle" in m.group(0), (
        "esRetrasada debe derivarse del semáforo, no de umbrales copiados"
    )


# ---------------------------------------------------------------------------
# Urgente y clasificación
# ---------------------------------------------------------------------------

@pytest.mark.skipif(shutil.which("node") is None, reason="node no está instalado")
@pytest.mark.parametrize(("columna", "valor", "urgente"), [
    ("PRIORIDAD", "URGENTE", True), ("PRIORIDADES", "URGENTE", True),
    ("PRIORIDADES", "urgente", True), ("PRIORIDADES", " URGENTE ", True),
    ("PRIORIDADES", "ALTA", False), ("PRIORIDADES", "", False),
])
def test_urgente_sale_de_la_columna_de_prioridad(columna, valor, urgente) -> None:
    guion = f"""
        {_entorno()}
        console.log(JSON.stringify(esUrgente({{ {json.dumps(columna)}: {json.dumps(valor)} }})));
    """
    assert _node(guion) is urgente


@pytest.mark.skipif(shutil.which("node") is None, reason="node no está instalado")
@pytest.mark.parametrize("columna", ["CLASIFICACION", "CLASI", "CLAS"])
def test_la_clasificacion_se_lee_con_sus_tres_nombres(columna: str) -> None:
    """El tracker la rotula `Clasi` y la vista de ventas `Clas`."""
    guion = f"""
        {_entorno()}
        console.log(JSON.stringify(clasificacionDe({{ {json.dumps(columna)}: 'AA' }})));
    """
    assert _node(guion) == "AA"


# ---------------------------------------------------------------------------
# El desglose
# ---------------------------------------------------------------------------

@pytest.mark.skipif(shutil.which("node") is None, reason="node no está instalado")
def test_el_desglose_cuenta_por_clasificacion() -> None:
    guion = f"""
        {_entorno()}
        console.log(JSON.stringify(desglosar([
            {{CLASI:'A'}}, {{CLASI:'A'}}, {{CLASI:'AA'}}, {{CLASI:'AAA'}}, {{CLASI:''}}
        ])));
    """
    assert _node(guion) == {"total": 5, "A": 2, "AA": 1, "AAA": 1}


@pytest.mark.skipif(shutil.which("node") is None, reason="node no está instalado")
def test_las_filas_sin_clasificar_cuentan_en_el_total_pero_no_en_el_desglose() -> None:
    """
    El desglose puede no sumar el total, y es correcto que así sea.

    En los datos reales hay filas sin clasificación. Repartirlas a la fuerza en
    A/AA/AAA sería inventar; esconderlas del total sería mentir sobre cuántas
    actividades hay.
    """
    guion = f"""
        {_entorno()}
        const d = desglosar([{{CLASI:'A'}}, {{CLASI:''}}, {{}}]);
        console.log(JSON.stringify([d.total, d.A + d.AA + d.AAA]));
    """
    assert _node(guion) == [3, 1]


# ---------------------------------------------------------------------------
# El rediseño no cambia ninguna regla
# ---------------------------------------------------------------------------

def test_el_semaforo_conserva_sus_umbrales() -> None:
    """El rediseño es visual: los seis números del semáforo no se tocan."""
    m = re.search(r"if\(t==='A'\) \{ limit=(\d+); buffer=(\d+); \}\s*"
                  r"else if\(t==='AA'\) \{ limit=(\d+); buffer=(\d+); \}\s*"
                  r"else if\(t==='AAA'\) \{ limit=(\d+); buffer=(\d+); \}", _fuente())
    assert m and m.groups() == ("3", "1", "15", "3", "30", "5")


def test_las_columnas_ocultas_siguen_ocultas() -> None:
    """El panel no puede haber reintroducido columnas técnicas en la vista."""
    from api.services.sheets import COLUMNAS_TECNICAS

    declaradas = re.search(r"const COLUMNAS_OCULTAS = \[[^\]]*\];", _fuente())
    assert declaradas
    ocultas = {c.upper() for c in re.findall(r"'([^']+)'", declaradas.group(0))}
    assert {c.upper() for c in COLUMNAS_TECNICAS} - ocultas == set()


def test_los_botones_de_la_barra_conservan_su_accion() -> None:
    """
    Cambia la forma, no lo que hacen. Estos cuatro `@click` son el contrato.

    Es la prueba que atrapa el fallo clásico de un rediseño: dejar el botón
    precioso y desconectado.
    """
    fuente = _fuente()
    for accion in ("loadTrackerData", "addNewRow", "saveAllTrackerRows", "toggleTrackerSort"):
        assert f'@click="{accion}"' in fuente, f"el botón de {accion} perdió su acción"


def test_el_panorama_solo_sale_en_la_vista_de_actividades() -> None:
    """En la tabla de cotizaciones no se pinta: sus indicadores son otros."""
    m = re.search(r'<div v-if="trackerSubView === \'TASKS\'" class="panorama', _fuente())
    assert m, "el panorama debe estar condicionado a la vista de actividades"
