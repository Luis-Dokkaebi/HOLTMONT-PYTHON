"""
`RELOJ` y `Días Finaliz. Cotiz` son el mismo contador: días transcurridos.

Regla del dueño (2026-08-07):

    Días Finaliz. Cotiz cuenta desde la fecha de inicio hasta hoy. Si F. Inicio
    dice miércoles 5 de agosto de 2026 y hoy es jueves 6, entonces vale 1. Lo
    mismo en el tracker con FECHA y RELOJ.

Son la misma función (`calculateDiasCounter`, index.html:7273) mirando columnas
distintas según la tabla que se esté viendo:

  * en un tracker el par es `FECHA` -> `RELOJ`;
  * en una hoja de ventas es `F. inicio` -> `Dias`.

No hay dos implementaciones. La función busca el **primer** encabezado de cada
lista que exista en la tabla, y las listas están ordenadas de forma que en cada
vista gane el correcto. Eso es justo lo frágil y lo que aquí se fija: si alguien
reordena `TASK_HEADER_MAP` o `QUOTE_HEADER_MAP`, o añade una columna `FECHA` a
la vista de cotizaciones, el contador empezaría a medir desde otra fecha sin que
nadie se entere.

El color de la celda lo pone `getTrafficStyle` a partir de la CLASIFICACIÓN, con
los mismos umbrales que el original (`REAL-HOLTMONT/index.html:7284-7286`):

    A    -> limite  3, margen 1
    AA   -> limite 15, margen 3
    AAA  -> limite 30, margen 5

    más del límite            -> rojo
    del (límite - margen) al límite -> amarillo
    por debajo                -> verde
    sin clasificación         -> sin color

Todo se comprueba evaluando las funciones **reales** extraídas de `index.html`
con Node. Una prueba que solo buscara cadenas pasaría con la lógica rota.
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

# Los encabezados reales de cada vista, en el orden en que los sirve la API
# (`TASK_HEADER_MAP` y `QUOTE_HEADER_MAP` de `api/services/sheets.py`), tal como
# se ven en la aplicación.
CABECERAS_TRACKER = [
    "FOLIO", "ALTA", "FECHA", "HORA", "CLASIFICACION", "CONCEPTO", "INVOLUCRADOS",
    "AVANCE %", "FECHA_ESTIMADA_FIN", "HORA_ESTIMADA_FIN", "RELOJ", "RESTRICCIONES",
    "PRIORIDADES", "RIESGOS", "FECHA_RESPUESTA", "CORREO", "CARPETA", "STATUS",
]
CABECERAS_VENTAS = [
    "FOLIO", "AREA", "CLIENTE", "CONCEPTO", "CLAS", "VENDEDOR",
    "F. VISITA", "F. INICIO", "F. ENTREGA", "DIAS", "AVANCE", "ESTATUS",
]


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


# ---------------------------------------------------------------------------
# El contador
# ---------------------------------------------------------------------------

def _guion_contador(cabeceras, fila) -> str:
    """Ejecuta `calculateDiasCounter` real sobre una fila dada."""
    cuerpo = _bloque(r"const calculateDiasCounter = \(row\) => \{.*?\n      \};",
                     "calculateDiasCounter")
    iscol = _bloque(r"const isCol = .*?;", "isCol")
    return f"""
        const staffTracker = {{ value: {{
            name: 'HOJA', headers: {json.dumps(cabeceras)} }} }};
        {iscol}
        {cuerpo}
        const row = {json.dumps(fila)};
        calculateDiasCounter(row);
        console.log(JSON.stringify(row));
    """


@pytest.mark.skipif(shutil.which("node") is None, reason="node no está instalado")
def test_en_el_tracker_el_par_es_fecha_y_reloj() -> None:
    """FECHA es de dónde cuenta; RELOJ es dónde escribe."""
    fila = {"FOLIO": "JO-1", "FECHA": "", "RELOJ": 0}
    # Una fecha de ayer: el contador tiene que dar exactamente 1.
    guion = _guion_contador(CABECERAS_TRACKER, fila).replace(
        '"FECHA": ""',
        '"FECHA": (d => `${String(d.getDate()).padStart(2,"0")}/`'
        ' + `${String(d.getMonth()+1).padStart(2,"0")}/`'
        ' + `${String(d.getFullYear()).slice(-2)}`)'
        '(new Date(Date.now() - 86400000))')
    resultado = _node(guion)
    assert resultado["RELOJ"] == 1, (
        f"con FECHA de ayer, RELOJ debe valer 1 y vale {resultado['RELOJ']}"
    )


@pytest.mark.skipif(shutil.which("node") is None, reason="node no está instalado")
def test_en_ventas_el_par_es_f_inicio_y_dias() -> None:
    """
    El ejemplo literal del dueño: F. Inicio ayer, hoy -> 1.

    Importa que **no** cuente desde `F. VISITA`, que va antes en la tabla: la
    lista de fechas no la incluye, y por eso el primer encabezado que casa es
    `F. INICIO`.
    """
    fila = {"FOLIO": "AV-1", "F. VISITA": "01/01/26", "F. INICIO": "", "DIAS": 0}
    guion = _guion_contador(CABECERAS_VENTAS, fila).replace(
        '"F. INICIO": ""',
        '"F. INICIO": (d => `${String(d.getDate()).padStart(2,"0")}/`'
        ' + `${String(d.getMonth()+1).padStart(2,"0")}/`'
        ' + `${String(d.getFullYear()).slice(-2)}`)'
        '(new Date(Date.now() - 86400000))')
    resultado = _node(guion)
    assert resultado["DIAS"] == 1, (
        f"con F. INICIO de ayer, DIAS debe valer 1 y vale {resultado['DIAS']}"
    )
    assert resultado["F. VISITA"] == "01/01/26", "F. VISITA no se toca"


@pytest.mark.skipif(shutil.which("node") is None, reason="node no está instalado")
@pytest.mark.parametrize(("dias_atras", "esperado"), [(0, 0), (1, 1), (7, 7), (207, 207)])
def test_el_contador_son_los_dias_transcurridos(dias_atras: int, esperado: int) -> None:
    """Hoy vale 0; cada día que pasa suma uno. Sin techo."""
    fila = {"FOLIO": "JO-1", "FECHA": "", "RELOJ": 0}
    guion = _guion_contador(CABECERAS_TRACKER, fila).replace(
        '"FECHA": ""',
        f'"FECHA": (d => `${{d.getFullYear()}}-`'
        f' + `${{String(d.getMonth()+1).padStart(2,"0")}}-`'
        f' + `${{String(d.getDate()).padStart(2,"0")}}`)'
        f'(new Date(Date.now() - {dias_atras} * 86400000))')
    assert _node(guion)["RELOJ"] == esperado


@pytest.mark.skipif(shutil.which("node") is None, reason="node no está instalado")
def test_una_fecha_futura_no_da_negativo() -> None:
    """`Math.max(0, …)`: una fecha de mañana cuenta 0, no -1."""
    fila = {"FOLIO": "JO-1", "FECHA": "", "RELOJ": 5}
    guion = _guion_contador(CABECERAS_TRACKER, fila).replace(
        '"FECHA": ""',
        '"FECHA": (d => `${d.getFullYear()}-`'
        ' + `${String(d.getMonth()+1).padStart(2,"0")}-`'
        ' + `${String(d.getDate()).padStart(2,"0")}`)'
        '(new Date(Date.now() + 86400000))')
    assert _node(guion)["RELOJ"] == 0


@pytest.mark.skipif(shutil.which("node") is None, reason="node no está instalado")
def test_sin_fecha_el_contador_no_toca_la_celda() -> None:
    """Una fila nueva sin fecha se queda en 0, no se inventa un número."""
    fila = {"FOLIO": "JO-1", "FECHA": "", "RELOJ": 0}
    assert _node(_guion_contador(CABECERAS_TRACKER, fila))["RELOJ"] == 0


@pytest.mark.skipif(shutil.which("node") is None, reason="node no está instalado")
@pytest.mark.parametrize("formato", ["05/08/26", "05/08/2026", "2026-08-05"])
def test_las_tres_grafias_de_fecha_cuentan_igual(formato: str) -> None:
    """
    `dd/mm/yy`, `dd/mm/yyyy` e ISO conviven en los datos reales.

    Se fija contra el 5 de agosto de 2026, el ejemplo del dueño, comparando las
    tres contra el mismo día calculado en JavaScript para no depender de la
    fecha en que corra la prueba.
    """
    fila = {"FOLIO": "JO-1", "FECHA": formato, "RELOJ": 0}
    guion = _guion_contador(CABECERAS_TRACKER, fila) + """
        const ref = new Date(2026, 7, 5);
        const hoy = new Date(); hoy.setHours(0,0,0,0); ref.setHours(0,0,0,0);
        console.log(JSON.stringify(Math.max(0, Math.round((hoy - ref) / 86400000))));
    """
    salida = subprocess.run(["node", "-e", guion], capture_output=True,
                            text=True, timeout=30, check=False)
    assert salida.returncode == 0, f"node falló: {salida.stderr}"
    fila_resultante, esperado = [json.loads(x) for x in salida.stdout.strip().splitlines()]
    assert fila_resultante["RELOJ"] == esperado


# ---------------------------------------------------------------------------
# El semáforo por clasificación
# ---------------------------------------------------------------------------

def _color(clasificacion: str, dias) -> str:
    cuerpo = _bloque(r"const getTrafficStyle = \(row\) => \{.*?\n      \};",
                     "getTrafficStyle")
    guion = f"""
        {cuerpo}
        const estilo = getTrafficStyle(
            {{ CLASIFICACION: {json.dumps(clasificacion)}, RELOJ: {json.dumps(dias)} }});
        const c = estilo.backgroundColor || '';
        console.log(JSON.stringify(
            c === '#e74c3c' ? 'rojo' :
            c === '#ffff00' ? 'amarillo' :
            c === '#2ecc71' ? 'verde' : 'sin color'));
    """
    return _node(guion)


@pytest.mark.skipif(shutil.which("node") is None, reason="node no está instalado")
@pytest.mark.parametrize(("clasificacion", "dias", "color"), [
    # A: limite 3, margen 1 -> verde <2, amarillo 2-3, rojo >3
    ("A", 0, "verde"), ("A", 1, "verde"), ("A", 2, "amarillo"),
    ("A", 3, "amarillo"), ("A", 4, "rojo"), ("A", 40, "rojo"),
    # AA: limite 15, margen 3 -> verde <12, amarillo 12-15, rojo >15
    ("AA", 0, "verde"), ("AA", 11, "verde"), ("AA", 12, "amarillo"),
    ("AA", 15, "amarillo"), ("AA", 16, "rojo"),
    # AAA: limite 30, margen 5 -> verde <25, amarillo 25-30, rojo >30
    ("AAA", 24, "verde"), ("AAA", 25, "amarillo"), ("AAA", 30, "amarillo"),
    ("AAA", 31, "rojo"),
])
def test_el_semaforo_sigue_la_clasificacion(clasificacion, dias, color) -> None:
    assert _color(clasificacion, dias) == color


@pytest.mark.skipif(shutil.which("node") is None, reason="node no está instalado")
@pytest.mark.parametrize("clasificacion", ["", "  ", "B", "URGENTE"])
def test_sin_clasificacion_valida_la_celda_no_se_pinta(clasificacion: str) -> None:
    """
    Solo A, AA y AAA tienen umbral. Lo demás se deja en blanco.

    Es deliberado y es lo que hace el original: pintar de rojo una fila sin
    clasificar diría que va tarde contra un plazo que nadie fijó.
    """
    assert _color(clasificacion, 999) == "sin color"


@pytest.mark.skipif(shutil.which("node") is None, reason="node no está instalado")
def test_los_umbrales_son_los_mismos_que_en_el_original() -> None:
    """
    Paridad con `REAL-HOLTMONT/index.html:7284-7286`.

    Se compara el texto de las tres líneas, que es donde viven los números. Si
    alguien afloja un plazo aquí, esta prueba lo enseña.
    """
    original = os.path.join(os.path.dirname(RAIZ), "REAL-HOLTMONT", "index.html")
    if not os.path.exists(original):
        pytest.skip("REAL-HOLTMONT no está disponible en este entorno")

    patron = re.compile(r"if\(t==='A'\) \{ limit=(\d+); buffer=(\d+); \}\s*"
                        r"else if\(t==='AA'\) \{ limit=(\d+); buffer=(\d+); \}\s*"
                        r"else if\(t==='AAA'\) \{ limit=(\d+); buffer=(\d+); \}")
    aqui = patron.search(_fuente())
    assert aqui, "no se encontraron los umbrales en index.html"

    with open(original, encoding="utf-8") as fh:
        alla = patron.search(fh.read())
    assert alla, "no se encontraron los umbrales en el original"
    assert aqui.groups() == alla.groups() == ("3", "1", "15", "3", "30", "5")
