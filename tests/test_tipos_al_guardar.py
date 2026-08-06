"""
Las columnas que el frontend edita con `<input type="number">`.

`index.html` pinta cuatro encabezados como campo numérico (línea 2616):

    <input v-else-if="isCol(h, ['DIAS','RELOJ','DÍAS FINALIZ. COTIZ',
                               'DIAS FINALIZ. COTIZ'])" type="number" ...>

Vue 3 aplica el modificador `.number` automáticamente sobre un `v-model` de un
input `type="number"`, así que esas celdas viajan como **número** en el JSON, no
como texto. Y no hace falta que el usuario las teclee: la vista las llena sola
con números en dos sitios.

  * `addNewRow` (index.html:8422) inicializa `row[h] = 0` para esas cuatro.
  * `calculateDiasCounter` (index.html:7315) escribe
    `row[hDias] = Math.max(0, diffDays)` sobre **cada** fila después de cada
    carga (index.html:8284), y `hDias` es el primer encabezado que casa con esa
    lista — en un tracker es `RELOJ`, porque `TASK_HEADER_MAP` no tiene `DIAS`.

De las cuatro, `DIAS` y `DÍAS FINALIZ. COTIZ` son columnas `integer` y ya pasan
por `a_entero`. `RELOJ` es `text` en las dos tablas (`TIPOS_REALES`), y sus
modelos de escritura la declaraban `Optional[str]` a secas: Pydantic rechaza un
`int` sobre un `str` y el lote entero moría con

    Fila inválida: 1 validation error for QuoteWrite
    reloj Input should be a valid string [type=string_type, input_value=0, ...]

Eso son los dos síntomas que reportó el dueño el 2026-08-06: no se podía dar de
alta ni asignar una cotización (fila nueva -> `RELOJ: 0`), y dar 100 % a una
actividad no la archivaba (el guardado se rechazaba, así que el avance nunca
llegaba a la base y `_esta_archivada` seguía leyendo el valor viejo).

La conversión va en el modelo, no en la vista: `index.html` es el original de
Apps Script y ahí ese número es legítimo — la hoja acepta cualquier tipo en
cualquier celda. Quien tiene que traducir la forma de hoja a la forma
relacional es `backend/schemas`, que es justo lo que ya hace con las fechas
`dd/mm/yy` y con los montos `"$ 1,250.50"`.
"""

from __future__ import annotations

import json
import os
import re
import shutil
import subprocess

import pytest

from api.services import tracker_store
from backend.core.engines.memoria import MemoryEngine
from backend.schemas.quote import QuoteWrite
from backend.schemas.task import TaskWrite
from backend.services.persistencia import PersistenciaTracker

RAIZ = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
INDEX = os.path.join(RAIZ, "index.html")

MODELOS = [QuoteWrite, TaskWrite]


def _ids(modelo) -> str:
    return modelo.__name__


# ---------------------------------------------------------------------------
# La lista numérica, leída del frontend
# ---------------------------------------------------------------------------

def _columnas_numericas_del_frontend() -> list[str]:
    """Los encabezados que `index.html` pinta como `<input type="number">`."""
    with open(INDEX, encoding="utf-8") as fh:
        fuente = fh.read()
    m = re.search(r"isCol\(h, (\[[^\]]*\])\)\" type=\"number\"", fuente)
    assert m, "no se encontró el `<input type=number>` de la tabla en index.html"
    return json.loads(m.group(1).replace("'", '"'))


def test_las_columnas_numericas_del_frontend_son_las_cuatro_conocidas() -> None:
    """
    Ancla la prueba al frontend real.

    Si alguien añade un encabezado a esa lista, esta prueba falla y obliga a
    comprobar que la columna correspondiente sabe recibir un número. Sin esto,
    el resto del archivo comprobaría una lista congelada a mano.
    """
    assert _columnas_numericas_del_frontend() == [
        "DIAS", "RELOJ", "DÍAS FINALIZ. COTIZ", "DIAS FINALIZ. COTIZ",
    ]


@pytest.mark.skipif(shutil.which("node") is None, reason="node no está instalado")
def test_una_fila_nueva_nace_con_esas_columnas_en_cero() -> None:
    """`addNewRow` las inicializa con el número `0`, no con `"0"`."""
    with open(INDEX, encoding="utf-8") as fh:
        fuente = fh.read()
    m = re.search(
        r"if \(isCol\(h, \['DIAS','RELOJ','DÍAS FINALIZ\. COTIZ','DIAS FINALIZ\. COTIZ'\]\)\) \{\n"
        r"\s*row\[h\] = (.+?);",
        fuente,
    )
    assert m, "no se encontró la inicialización de `addNewRow` en index.html"
    salida = subprocess.run(["node", "-e", f"console.log(typeof ({m.group(1)}))"],
                            capture_output=True, text=True, timeout=30, check=False)
    assert salida.returncode == 0, f"node falló: {salida.stderr}"
    assert salida.stdout.strip() == "number"


# ---------------------------------------------------------------------------
# `RELOJ` es `text` y tiene que aceptar el número
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("modelo", MODELOS, ids=_ids)
@pytest.mark.parametrize(("entrada", "esperado"), [
    (0, "0"),          # fila recién creada por `addNewRow`
    (7, "7"),          # días transcurridos que escribe `calculateDiasCounter`
    (103, "103"),
    (70.5, "70.5"),    # el input numérico admite decimales
])
def test_reloj_acepta_el_numero_que_manda_el_input(modelo, entrada, esperado) -> None:
    fila = modelo.desde_hoja({"FOLIO": "X-1", "RELOJ": entrada})
    assert fila.reloj == esperado


@pytest.mark.parametrize("modelo", MODELOS, ids=_ids)
@pytest.mark.parametrize("texto", ["17:00:00", "70.0", "", "  "])
def test_reloj_conserva_el_texto_tal_cual(modelo, texto) -> None:
    """
    En los datos reales conviven horas (`"17:00:00"`) y números (`"70.0"`).

    La conversión solo toca los números; un texto que ya venía como texto no se
    reinterpreta ni se recorta, que es lo que documenta el propio campo.
    """
    assert modelo.desde_hoja({"FOLIO": "X-1", "RELOJ": texto}).reloj == texto


@pytest.mark.parametrize("modelo", MODELOS, ids=_ids)
def test_reloj_vacio_sigue_siendo_nulo(modelo) -> None:
    assert modelo.desde_hoja({"FOLIO": "X-1", "RELOJ": None}).reloj is None


@pytest.mark.parametrize("modelo", MODELOS, ids=_ids)
def test_reloj_no_acepta_cualquier_cosa(modelo) -> None:
    """
    La tolerancia es a números, no a estructuras.

    Un `dict` o una lista en esa celda sigue siendo un error de validación: si
    se convirtiera con `str()` se guardaría `"{'a': 1}"` en la base, que es
    exactamente el descarte silencioso que `extra="forbid"` viene a evitar.
    """
    with pytest.raises(Exception):
        modelo.desde_hoja({"FOLIO": "X-1", "RELOJ": {"a": 1}})


# ---------------------------------------------------------------------------
# Los dos síntomas que reportó el dueño, de punta a punta
# ---------------------------------------------------------------------------

SEMILLA_TASK = {
    "id": "11111111-1111-1111-1111-111111111111",
    "dedupe_key": "JAIME OLIVO::JO-0001",
    "folio": "JO-0001",
    "source_sheet": "JAIME OLIVO",
    "concepto": "REVISAR PLANOS",
    "assignee_raw": "JAIME OLIVO",
    "avance": 0.0,
    "status": "ASIGNADO",
    "reloj": "3",
    "carpeta": "https://drive.google.com/x",
    "correo": "https://drive.google.com/y",
}


@pytest.fixture
def tracker(monkeypatch):
    motor = MemoryEngine({
        "tasks": [dict(SEMILLA_TASK)],
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


def test_se_puede_dar_de_alta_una_cotizacion_recien_creada(tracker):
    """Síntoma 1: alta/asignación de cotización con la fila tal como nace."""
    respuesta = tracker_store.save_tracker_batch(
        "ANTONIA_VENTAS",
        [{"FOLIO": "AV-9001", "CLIENTE": "ACME", "CONCEPTO": "COTIZAR NAVE",
          "VENDEDOR": "ANTONIA", "AVANCE": "0", "ESTATUS": "ASIGNADO",
          "RELOJ": 0, "DIAS": 0, "_tempId": "tmp-1"}],
        username="ANTONIA_VENTAS",
    )

    assert respuesta["success"] is True, respuesta.get("message")
    fila = [f for f in tracker.select("quotes") if f["folio"] == "AV-9001"][0]
    assert fila["reloj"] == "0"


def test_dar_cien_por_ciento_persiste_el_avance_y_archiva_la_tarea(tracker):
    """
    Síntoma 2: el 100 % no se archivaba porque el guardado nunca llegaba.

    La fila viaja con el `RELOJ` numérico que `calculateDiasCounter` le acaba
    de escribir, igual que en la aplicación. Se comprueba lo que ve el usuario:
    que la matriz de la hoja mete la tarea bajo `TAREAS REALIZADAS`.
    """
    from api.services.sheets import SEPARADOR_ARCHIVO, _valores_de_tareas

    respuesta = tracker_store.save_tracker_batch(
        "JAIME OLIVO",
        [{"FOLIO": "JO-0001", "CONCEPTO": "REVISAR PLANOS",
          "RESPONSABLE": "JAIME OLIVO", "AVANCE": "100", "ESTATUS": "ASIGNADO",
          "RELOJ": 12}],
        username="JAIME_OLIVO",
    )

    assert respuesta["success"] is True, respuesta.get("message")
    fila = [f for f in tracker.select("tasks") if f["folio"] == "JO-0001"][0]
    assert fila["avance"] == 100.0
    assert fila["reloj"] == "12"

    valores = _valores_de_tareas(tracker.select("tasks"))
    assert any(SEPARADOR_ARCHIVO in celda for celda in valores[1]), (
        f"la tarea al 100 % no quedó bajo {SEPARADOR_ARCHIVO}: {valores}"
    )
