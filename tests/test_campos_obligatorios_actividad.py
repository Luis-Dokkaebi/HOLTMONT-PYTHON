"""
Toda actividad nueva nace con PRIORIDAD, RIESGOS y FEC. EST. FIN.

Es una regla de control, no de forma: el dueño no puede priorizar ni medir el
compromiso de una tarea que nace sin prioridad, sin riesgo y sin fecha estimada
de fin. Hasta hoy los tres campos eran opcionales y la tabla se llenaba de filas
que nadie podía ordenar — la columna `Fec. Est. Fin` de la vista del Tracker
está vacía en la práctica totalidad de las filas.

Se cubren las tres capas por separado porque fallan por separado:

  1. **Las reglas** (`api/services/tracker_rules.py`): el catálogo de valores y
     qué falta en una fila. Es el gemelo en Python de `CODIGO.js` (AGENTS.md §6).
  2. **El guardado** (`api/services/tracker_store.py`): que una actividad nueva
     incompleta se rechace **antes** de escribir nada, no después.
  3. **La vista** (`index.html`): que los desplegables existan en el Tracker —
     el reporte original es que al dar de alta desde "NUEVA ACTIVIDAD" no salía
     el selector de riesgo— y que ofrezcan el catálogo completo.

`URGENTE` y `CATASTROFICO` son los dos valores que se estrenan. Antes vivían
solo en algunas vistas (el desplegable del Tracker tenía `URGENTE`; el del PPC
Maestro, no), así que el mismo dato se capturaba con vocabularios distintos
según la pantalla.

Qué NO exige esta regla: nada sobre las filas que ya existen. El candado mira
solo las actividades **nuevas** (sin folio). Una fila vieja e incompleta se
sigue pudiendo editar y guardar; obligar a completarla dejaría al equipo sin
poder tocar su propio historial.

Tampoco exige nada **a una tabla que no tiene esas columnas**. Cotizaciones no
maneja PRIORIDAD, RIESGOS ni FEC. EST. FIN —sus encabezados son otros: `PRIO.
COT.`, `F. VISITA`, `F. INICIO`, `F. ENTREGA`—, así que allí el candado pedía
tres datos que la pantalla no tiene dónde capturar y ninguna cotización nueva se
podía guardar. La regla es del Tracker; se decide por las columnas de la hoja
destino y no por el nombre de la pantalla, porque la columna es el hecho: la que
no existe no se puede llenar.
"""

from __future__ import annotations

import json
import os
import re
import shutil
import subprocess

import pytest

from api.services import tracker_rules as rules
from api.services import tracker_store
from backend.core.engines.memoria import MemoryEngine
from backend.services.persistencia import PersistenciaTracker

RAIZ = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
INDEX = os.path.join(RAIZ, "index.html")
CODIGO = os.path.join(RAIZ, "CODIGO.js")


def _leer(ruta: str) -> str:
    with open(ruta, encoding="utf-8") as fh:
        return fh.read()


# ---------------------------------------------------------------------------
# 1. El catálogo
# ---------------------------------------------------------------------------

def test_el_catalogo_de_prioridades_incluye_urgente():
    assert rules.PRIORIDADES_VALIDAS == ("BAJA", "MEDIA", "ALTA", "URGENTE")


def test_el_catalogo_de_riesgos_incluye_catastrofico():
    assert rules.RIESGOS_VALIDOS == ("BAJO", "MEDIO", "ALTO", "CATASTROFICO")


# ---------------------------------------------------------------------------
# 2. Qué es una actividad nueva y qué le falta
# ---------------------------------------------------------------------------

def test_sin_folio_la_actividad_es_nueva():
    assert rules.es_actividad_nueva({"CONCEPTO": "REVISAR PLANOS"}) is True


@pytest.mark.parametrize("fila", [
    {"FOLIO": "JO-0001"},
    {"ID": "JO-0001"},
    {"folio": "jo-0001"},
])
def test_con_folio_la_actividad_ya_existe(fila):
    """El folio lo pone el backend al dar de alta: tenerlo es haber nacido ya."""
    assert rules.es_actividad_nueva(fila) is False


def test_una_actividad_vacia_debe_los_tres_campos():
    assert rules.campos_obligatorios_faltantes({}) == [
        "PRIORIDAD", "RIESGOS", "FEC. EST. FIN"]


def test_una_actividad_completa_no_debe_nada():
    fila = {"CONCEPTO": "COTIZAR NAVE", "PRIORIDAD": "URGENTE",
            "RIESGOS": "CATASTROFICO", "FEC. EST. FIN": "30/08/26"}
    assert rules.campos_obligatorios_faltantes(fila) == []


@pytest.mark.parametrize("fila", [
    # La vista rotula las columnas de varias formas según la hoja; el candado
    # lee por alias, igual que el resto del motor de reglas.
    {"PRIORIDADES": "ALTA", "RIESGO": "MEDIO", "FECHA ESTIMADA DE FIN": "30/08/26"},
    {"prioridad": "alta", "riesgos": "medio", "fecha_estimada_fin": "2026-08-30"},
    {"PRIORIDAD": " ALTA ", "RIESGOS": " MEDIO ", "FEC. EST. FIN": " 30/08/26 "},
])
def test_los_alias_y_los_espacios_cuentan_igual(fila):
    assert rules.campos_obligatorios_faltantes(fila) == []


def test_un_espacio_en_blanco_no_es_un_valor():
    fila = {"PRIORIDAD": "   ", "RIESGOS": "ALTO", "FEC. EST. FIN": "30/08/26"}
    assert rules.campos_obligatorios_faltantes(fila) == ["PRIORIDAD"]


@pytest.mark.parametrize("valor", ["NORMAL", "ESTRATEGICA", "SI", "3"])
def test_una_prioridad_fuera_del_catalogo_no_sirve_para_priorizar(valor):
    """
    Es el motivo de la regla: si se admite cualquier texto, la columna deja de
    ordenar. El desplegable del Tracker ofrecía `NORMAL` y `ESTRATEGICA`, que
    ninguna otra vista conocía ni ninguna métrica sabía contar.
    """
    fila = {"PRIORIDAD": valor, "RIESGOS": "ALTO", "FEC. EST. FIN": "30/08/26"}
    assert rules.campos_obligatorios_faltantes(fila) == ["PRIORIDAD"]


def test_un_riesgo_fuera_del_catalogo_tampoco():
    fila = {"PRIORIDAD": "ALTA", "RIESGOS": "REGULAR", "FEC. EST. FIN": "30/08/26"}
    assert rules.campos_obligatorios_faltantes(fila) == ["RIESGOS"]


def test_la_fecha_respuesta_no_sustituye_a_la_fecha_estimada_de_fin():
    """
    Son dos columnas distintas de la misma vista y el control que se pidió es
    sobre `Fec. Est. Fin`, que es la que estaba vacía.
    """
    fila = {"PRIORIDAD": "ALTA", "RIESGOS": "ALTO", "FECHA RESPUESTA": "30/08/26"}
    assert rules.campos_obligatorios_faltantes(fila) == ["FEC. EST. FIN"]


# ---------------------------------------------------------------------------
# 2 bis. Una columna que no existe no se puede exigir
# ---------------------------------------------------------------------------

def test_el_tracker_exige_los_tres_campos_porque_tiene_las_tres_columnas():
    fila = {"CONCEPTO": "REVISAR PLANOS", "RESPONSABLE": "JAIME OLIVO"}
    assert rules.campos_obligatorios_faltantes(
        fila, tracker_store.ENCABEZADOS_TAREA) == ["PRIORIDAD", "RIESGOS", "FEC. EST. FIN"]


def test_cotizaciones_no_tiene_esas_columnas_y_no_se_le_exigen():
    """
    El defecto reportado: dar de alta una cotización devolvía "Falta PRIORIDAD,
    RIESGOS, FEC. EST. FIN" y no se podía guardar nada. La tabla de ventas no
    tiene esas columnas —lleva `PRIO. COT.`, `F. VISITA`, `F. INICIO` y
    `F. ENTREGA`—, así que el usuario no tenía dónde escribir lo que se le pedía.
    """
    fila = {"CLIENTE": "NEMAK", "CONCEPTO": "COTIZAR NAVE", "VENDEDOR": "ANTONIA VENTAS"}
    assert rules.campos_obligatorios_faltantes(
        fila, tracker_store.ENCABEZADOS_VENTAS) == []


def test_una_columna_presente_pero_vacia_si_se_exige():
    """
    La excepción es por columna inexistente, no por celda vacía: si la hoja
    tiene la columna, dejarla en blanco sigue siendo un alta incompleta.
    """
    fila = {"CONCEPTO": "REVISAR PLANOS", "PRIORIDAD": "", "RIESGOS": "BAJO",
            "FEC. EST. FIN": "30/08/26"}
    assert rules.campos_obligatorios_faltantes(fila, ["CONCEPTO", "PRIORIDAD",
                                                     "RIESGOS", "FEC. EST. FIN"]) == ["PRIORIDAD"]


def test_sin_lista_de_columnas_se_exigen_los_tres():
    """
    Sin saber qué columnas tiene la hoja, el control es el estricto: es lo que
    aplica cuando no se pudo leer el encabezado, y ante la duda no se abre.
    """
    assert rules.campos_obligatorios_faltantes({"CONCEPTO": "X"}, None) == [
        "PRIORIDAD", "RIESGOS", "FEC. EST. FIN"]


def test_el_mensaje_nombra_lo_que_falta():
    mensaje = rules.mensaje_campos_obligatorios(["PRIORIDAD", "FEC. EST. FIN"])
    assert "falta PRIORIDAD, FEC. EST. FIN" in mensaje


# ---------------------------------------------------------------------------
# 3. El guardado rechaza antes de escribir
# ---------------------------------------------------------------------------

SEMILLA = {
    "id": "11111111-1111-1111-1111-111111111111",
    "dedupe_key": "JAIME OLIVO::JO-0001",
    "folio": "JO-0001",
    "source_sheet": "JAIME OLIVO",
    "concepto": "REVISAR PLANOS",
    "assignee_raw": "JAIME OLIVO",
    "avance": 0.0,
    "status": "ASIGNADO",
}


@pytest.fixture
def tracker(monkeypatch):
    motor = MemoryEngine({
        "tasks": [dict(SEMILLA)],
        "quotes": [],
        "people": [],
        "plan_semanal": [],
        "task_involucrados": [],
        "system_log": [],
    })
    monkeypatch.setattr(tracker_store, "_persistencia", lambda: PersistenciaTracker(motor))
    monkeypatch.setattr(
        tracker_store, "read_values",
        lambda hoja: [["FOLIO", "CONCEPTO", "RESPONSABLE", "AVANCE", "ESTATUS", "RELOJ"]],
    )
    return motor


def test_una_actividad_nueva_incompleta_no_se_guarda(tracker):
    respuesta = tracker_store.save_tracker_batch(
        "JAIME OLIVO",
        [{"CONCEPTO": "TAREA SIN CONTROL", "RESPONSABLE": "JAIME OLIVO",
          "_tempId": "tmp-1"}],
        username="JAIME_OLIVO",
    )

    assert respuesta["success"] is False
    assert "PRIORIDAD" in respuesta["message"]
    assert "RIESGOS" in respuesta["message"]
    assert "FEC. EST. FIN" in respuesta["message"]
    # Y no queda rastro: el rechazo es antes de escribir, no un rollback.
    assert [f for f in tracker.select("tasks") if f["concepto"] == "TAREA SIN CONTROL"] == []


def test_una_actividad_nueva_completa_se_guarda(tracker):
    respuesta = tracker_store.save_tracker_batch(
        "JAIME OLIVO",
        [{"CONCEPTO": "TAREA CONTROLADA", "RESPONSABLE": "JAIME OLIVO",
          "PRIORIDADES": "URGENTE", "RIESGOS": "CATASTROFICO",
          "FEC. EST. FIN": "30/08/26", "_tempId": "tmp-2"}],
        username="JAIME_OLIVO",
    )

    assert respuesta["success"] is True, respuesta.get("message")
    filas = [f for f in tracker.select("tasks") if f["concepto"] == "TAREA CONTROLADA"]
    assert len(filas) == 1
    assert filas[0]["prioridad"] == "URGENTE"
    assert filas[0]["riesgos"] == "CATASTROFICO"


def test_una_fila_que_ya_existe_se_sigue_editando_sin_los_tres_campos(tracker):
    """El candado es para dar de alta. El historial no se toca."""
    respuesta = tracker_store.save_tracker_batch(
        "JAIME OLIVO",
        [{"FOLIO": "JO-0001", "CONCEPTO": "REVISAR PLANOS", "AVANCE": "50"}],
        username="JAIME_OLIVO",
    )

    assert respuesta["success"] is True, respuesta.get("message")
    fila = next(f for f in tracker.select("tasks") if f["folio"] == "JO-0001")
    assert fila["avance"] == 50.0


def test_un_renglon_en_blanco_no_bloquea_el_lote(tracker):
    """
    "NUEVA ACTIVIDAD" deja renglones vacíos y "Guardar Todo" los manda con el
    resto. Exigirle prioridad a una fila que nadie llenó bloquearía el lote
    entero por algo que ni siquiera es una actividad.
    """
    respuesta = tracker_store.save_tracker_batch(
        "JAIME OLIVO",
        [{"CONCEPTO": "TAREA BUENA", "PRIORIDAD": "ALTA", "RIESGOS": "BAJO",
          "FEC. EST. FIN": "30/08/26", "_tempId": "tmp-5"},
         {"CONCEPTO": "", "RESPONSABLE": "", "_tempId": "tmp-6"}],
        username="JAIME_OLIVO",
    )

    assert respuesta["success"] is True, respuesta.get("message")
    assert len([f for f in tracker.select("tasks") if f["concepto"] == "TAREA BUENA"]) == 1


@pytest.fixture
def cotizaciones(monkeypatch):
    """La tabla de ventas: sus encabezados no incluyen ninguno de los tres."""
    motor = MemoryEngine({
        "tasks": [],
        "quotes": [],
        "people": [],
        "plan_semanal": [],
        "task_involucrados": [],
        "system_log": [],
    })
    monkeypatch.setattr(tracker_store, "_persistencia", lambda: PersistenciaTracker(motor))
    monkeypatch.setattr(
        tracker_store, "read_values",
        lambda hoja: [list(tracker_store.ENCABEZADOS_VENTAS)],
    )
    return motor


def test_una_cotizacion_nueva_se_guarda_sin_prioridad_ni_riesgos(cotizaciones):
    """
    El defecto reportado, en la capa que escribe: la tabla de cotizaciones no
    tiene esas columnas, así que exigirlas dejaba a Ventas sin poder dar de alta.
    """
    respuesta = tracker_store.save_tracker_batch(
        "ANTONIA_VENTAS",
        [{"CLIENTE": "NEMAK", "CONCEPTO": "COTIZAR NAVE INDUSTRIAL",
          "VENDEDOR": "ANTONIA VENTAS", "_tempId": "tmp-cot-1"}],
        username="ANTONIA_VENTAS",
    )

    assert respuesta["success"] is True, respuesta.get("message")
    filas = [f for f in cotizaciones.select("quotes")
             if f["concepto"] == "COTIZAR NAVE INDUSTRIAL"]
    assert len(filas) == 1


def test_el_lote_entero_se_rechaza_si_una_actividad_nueva_esta_incompleta(tracker):
    """
    Guardar la mitad del lote deja al usuario sin saber qué se escribió. Es el
    mismo criterio que ya usa la papa caliente cuando una fase está en curso.
    """
    respuesta = tracker_store.save_tracker_batch(
        "JAIME OLIVO",
        [{"CONCEPTO": "COMPLETA", "PRIORIDAD": "ALTA", "RIESGOS": "BAJO",
          "FEC. EST. FIN": "30/08/26", "_tempId": "tmp-3"},
         {"CONCEPTO": "INCOMPLETA", "_tempId": "tmp-4"}],
        username="JAIME_OLIVO",
    )

    assert respuesta["success"] is False
    assert [f for f in tracker.select("tasks") if f["concepto"] == "COMPLETA"] == []


# ---------------------------------------------------------------------------
# 4. La vista: los desplegables del Tracker y del PPC Maestro
# ---------------------------------------------------------------------------

@pytest.fixture(scope="module")
def vista() -> str:
    return _leer(INDEX)


def _catalogo_declarado(vista: str, nombre: str) -> list:
    """El arreglo literal `const NOMBRE = [...]` que declara la vista."""
    m = re.search(rf"const {nombre} = \[([^\]]*)\];", vista)
    assert m, f"{nombre} no está declarado en index.html"
    return [v.strip().strip("'\"") for v in m.group(1).split(",")]


def _selects_tras(fuente: str, marca: str, cuantos: int = 1) -> list:
    """Los `<select>` que siguen a una marca de plantilla."""
    pos = fuente.index(marca)
    bloques = []
    for _ in range(cuantos):
        apertura = fuente.index("<select", pos)
        cierre = fuente.index("</select>", apertura)
        bloques.append(fuente[apertura:cierre])
        pos = cierre
    return bloques


def test_la_vista_declara_el_mismo_catalogo_que_el_backend(vista):
    assert _catalogo_declarado(vista, "PRIORIDADES_VALIDAS") == list(rules.PRIORIDADES_VALIDAS)
    assert _catalogo_declarado(vista, "RIESGOS_VALIDOS") == list(rules.RIESGOS_VALIDOS)


def test_el_tracker_pinta_el_desplegable_de_prioridad_desde_el_catalogo(vista):
    bloque = _selects_tras(vista, "CATALOGO_PRIORIDAD_TRACKER")[0]
    assert 'v-for="opt in priorityOpts"' in bloque
    # NORMAL y ESTRATEGICA estaban escritos a mano y no existían en ninguna otra
    # vista ni en ninguna métrica.
    assert "ESTRATEGICA" not in bloque and ">NORMAL<" not in bloque


def test_el_tracker_pinta_el_desplegable_de_riesgo(vista):
    """
    El defecto reportado: al dar de alta desde "NUEVA ACTIVIDAD" la celda de
    riesgo era un campo de texto libre, sin desplegable.
    """
    bloque = _selects_tras(vista, "CATALOGO_RIESGO_TRACKER")[0]
    assert 'v-for="opt in riskOpts"' in bloque


def test_el_ppc_maestro_usa_los_mismos_dos_catalogos(vista):
    prioridad, riesgo = _selects_tras(vista, "CATALOGO_PRIORIDAD_PPC", cuantos=2)
    assert 'v-for="opt in priorityOpts"' in prioridad
    assert 'v-for="opt in riskOpts"' in riesgo


def test_la_vista_no_deja_guardar_una_actividad_nueva_incompleta(vista):
    """
    Las tres puertas de guardado del Tracker y del PPC pasan por el mismo
    validador. Una que se olvide manda al backend una fila que va a rebotar.
    """
    for guardado in ("const saveRow", "const saveAllTrackerRows", "const submitBatch"):
        inicio = vista.index(guardado)
        assert "camposObligatoriosFaltantes" in vista[inicio:inicio + 3000], (
            f"{guardado} no valida los campos obligatorios")


def test_la_vista_valida_contra_las_columnas_de_la_tabla_que_esta_abierta(vista):
    """
    El aviso salía en Cotizaciones, que no tiene ninguna de las tres columnas.
    Las dos puertas del Tracker validan contra los encabezados de la tabla
    abierta; sin ellos el validador pide columnas que esa pantalla no tiene.
    """
    for guardado in ("const saveRow", "const saveAllTrackerRows"):
        inicio = vista.index(guardado)
        bloque = vista[inicio:inicio + 3000]
        assert "camposObligatoriosFaltantes(row, staffTracker.value.headers)" in bloque, (
            f"{guardado} valida sin mirar las columnas de la tabla")


# ---------------------------------------------------------------------------
# 5. Paridad con el backend de Apps Script
# ---------------------------------------------------------------------------

def test_codigo_js_declara_el_mismo_catalogo():
    """
    `CODIGO.js` es el backend en producción (AGENTS.md §1): si los catálogos se
    separan, la vista ofrece un valor que el backend rechaza.
    """
    codigo = _leer(CODIGO)
    for valor in rules.PRIORIDADES_VALIDAS:
        assert f"'{valor}'" in codigo, f"falta {valor} en el catálogo de CODIGO.js"
    for valor in rules.RIESGOS_VALIDOS:
        assert f"'{valor}'" in codigo, f"falta {valor} en el catálogo de CODIGO.js"


def test_codigo_js_cierra_las_dos_puertas_de_guardado():
    codigo = _leer(CODIGO)
    for funcion in ("function internalUpdateTask", "function apiSaveTrackerBatch"):
        inicio = codigo.index(funcion)
        assert "motivoDeRechazoDeAlta" in codigo[inicio:inicio + 6000], (
            f"{funcion} guarda actividades nuevas sin validar")


@pytest.mark.skipif(not shutil.which("node"), reason="node no está instalado")
def test_el_validador_de_codigo_js_da_el_mismo_veredicto_que_python(tmp_path):
    """
    Paridad ejecutable, no textual: se corre el validador real de `CODIGO.js`
    sobre los mismos casos y se comparan los veredictos.
    """
    codigo = _leer(CODIGO)
    inicio = codigo.index("// === INICIO CONTROL DE ALTA")
    fin = codigo.index("// === FIN CONTROL DE ALTA")

    # (fila, columnas de la hoja destino). `null` = no se supo leer el
    # encabezado, que es el caso estricto.
    casos = [
        [{}, None],
        [{"PRIORIDAD": "URGENTE", "RIESGOS": "CATASTROFICO", "FEC. EST. FIN": "30/08/26"}, None],
        [{"PRIORIDADES": "ALTA", "RIESGO": "MEDIO", "FECHA ESTIMADA DE FIN": "30/08/26"}, None],
        [{"PRIORIDAD": "NORMAL", "RIESGOS": "ALTO", "FEC. EST. FIN": "30/08/26"}, None],
        [{"PRIORIDAD": "ALTA", "RIESGOS": "ALTO", "FECHA RESPUESTA": "30/08/26"}, None],
        [{"CONCEPTO": "REVISAR PLANOS"}, list(tracker_store.ENCABEZADOS_TAREA)],
        [{"CLIENTE": "NEMAK", "CONCEPTO": "COTIZAR NAVE"}, list(tracker_store.ENCABEZADOS_VENTAS)],
        [{"CONCEPTO": "X", "PRIORIDAD": "", "RIESGOS": "BAJO", "FEC. EST. FIN": "30/08/26"},
         ["CONCEPTO", "PRIORIDAD", "RIESGOS", "FEC. EST. FIN"]],
    ]

    guion = tmp_path / "paridad.js"
    guion.write_text(
        codigo[inicio:fin]
        + f"\nconsole.log(JSON.stringify({json.dumps(casos)}"
        + ".map(function (caso) { return camposObligatoriosFaltantes(caso[0], caso[1]); })));",
        encoding="utf-8")

    salida = subprocess.run(["node", str(guion)], capture_output=True, text=True, check=True)
    assert json.loads(salida.stdout) == [
        rules.campos_obligatorios_faltantes(fila, columnas) for fila, columnas in casos]
