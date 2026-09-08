"""
Al asignar una Pre Work Order, la cotización viaja con ella.

Reporte del dueño (2026-09-08):

    «Verifica que se pueda mandar la prework order a cualquier persona que se
    asigne a su tracker, y le aparezca la cotización como adjunto cuando se le
    asigne y se mande la prework order.»

Lo que estaba mal
-----------------
El formulario junta en `archivoUrl` los documentos de la orden —la cotización
subida, los planos, los archivos de validación de diseño— y
`process_and_save_work_order` los pone en `ARCHIVO` de la **fila de cabecera**,
que es la de quien elaboró la orden. `ARCHIVO` es alias de la columna `carpeta`
(`backend/schemas/task.py`), la que el Tracker pinta como adjunto.

Pero `tareas_de_programa` —la función que convierte cada renglón del programa
en la tarea de su responsable— construía la fila con nueve campos y ninguno era
`ARCHIVO`. Resultado medido: quien ejecuta el trabajo recibía la tarea en su
tracker con `carpeta = None`, es decir, sin la cotización ni ningún otro
documento de la orden, mientras el cotizador sí los tenía. La persona asignada
veía el concepto y la fecha, y para ver qué se cotizó tenía que ir a pedirlo.

Aquí se fija que el adjunto acompaña a **cada** persona asignada, sea o no del
organigrama, y que sigue estando en la cabecera como hasta ahora.
"""

from __future__ import annotations

import os
import sys
from typing import Any, Dict, List

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from api.services import work_order  # noqa: E402
from backend.core.engines.memoria import MemoryEngine  # noqa: E402
from backend.services.persistencia import PersistenciaTracker  # noqa: E402

COTIZACION = "https://drive.google.com/file/d/COTIZACION-ACME-1001/view"
PLANO = "https://drive.google.com/file/d/[DISENO-pdf] PLANO-1/view"

CABECERA = {
    "FOLIO": "1001AC Electro 060826",
    "AREA": "ELECTROMECANICA",
    "CLASIFICACION": "AA",
    "FECHA": "06/08/26",
    "ARCHIVO": COTIZACION,
}


def _linea(**campos: Any) -> Dict[str, Any]:
    base = {
        "description": "MONTAR TABLERO",
        "seccion": "TRABAJO",
        "responsable": "TERESA GARZA",
        "fechaEntrega": "20/08/26",
    }
    base.update(campos)
    return base


# ----------------------------------------------------------------------
# 1. La fila derivada lleva el adjunto
# ----------------------------------------------------------------------

def test_la_linea_de_programa_hereda_el_adjunto_de_la_orden():
    ((_, fila),) = work_order.tareas_de_programa([_linea()], CABECERA)

    assert fila["ARCHIVO"] == COTIZACION, (
        "La persona asignada recibe la tarea sin la cotización: el adjunto se "
        "queda solo en la fila de quien cotizó")


def test_cada_responsable_de_una_linea_recibe_el_adjunto():
    """Tres personas en un renglón: tres tareas, las tres con la cotización."""
    derivadas = work_order.tareas_de_programa(
        [_linea(responsable=["TERESA GARZA", "ANGEL SALINAS", "JAIME OLIVO"])],
        CABECERA)

    assert len(derivadas) == 3
    for hoja, fila in derivadas:
        assert fila["ARCHIVO"] == COTIZACION, f"{hoja} se quedó sin el adjunto"


def test_una_orden_sin_documentos_no_inventa_un_adjunto():
    sin_archivo = {k: v for k, v in CABECERA.items() if k != "ARCHIVO"}

    ((_, fila),) = work_order.tareas_de_programa([_linea()], sin_archivo)

    assert fila["ARCHIVO"] == ""


def test_varios_documentos_viajan_completos():
    """
    El formulario manda cotización y planos separados por saltos de línea
    (`archivoUrl: [...files, ...designFiles].join('\\n')`). Se copian tal cual:
    partirlos aquí dejaría fuera todo menos el primero.
    """
    cabecera = dict(CABECERA, ARCHIVO=f"{COTIZACION}\n{PLANO}")

    ((_, fila),) = work_order.tareas_de_programa([_linea()], cabecera)

    assert fila["ARCHIVO"] == f"{COTIZACION}\n{PLANO}"


# ----------------------------------------------------------------------
# 2. De punta a punta contra la base
# ----------------------------------------------------------------------

def _motor() -> MemoryEngine:
    return MemoryEngine({
        "quotes": [], "tasks": [], "people": [], "plan_semanal": [],
        "task_involucrados": [], "system_log": [], "work_orders": [],
        "wo_programa": [],
    })


@pytest.fixture
def base(monkeypatch):
    motor = _motor()
    monkeypatch.setattr(work_order, "_persistencia", lambda: PersistenciaTracker(motor))
    monkeypatch.setattr(work_order, "_engine", lambda: motor)
    monkeypatch.setattr(work_order, "save_to_obsidian", lambda *a, **k: None)
    monkeypatch.setattr(work_order, "get_next_sequence", lambda *a, **k: "1001")
    return motor


def _orden(**campos: Any) -> Dict[str, Any]:
    base = {
        "cliente": "ACME CORP",
        "especialidad": "ELECTROMECANICA",
        "concepto": "LEVANTAMIENTO DE NAVE",
        "clasificacion": "AA",
        "responsable": "ADMINISTRADOR",
        "archivoUrl": COTIZACION,
        "programa": [_linea()],
    }
    base.update(campos)
    return base


def _tareas_de(motor: MemoryEngine, hoja: str) -> List[Dict[str, Any]]:
    return [f for f in motor.select("tasks") if f.get("source_sheet") == hoja]


def test_la_persona_asignada_ve_la_cotizacion_en_su_tracker(base):
    respuesta = work_order.process_and_save_work_order([_orden()], "PREWORK_ORDER")
    assert respuesta["success"] is True, respuesta.get("message")

    (tarea,) = _tareas_de(base, "TERESA GARZA")
    assert tarea["carpeta"] == COTIZACION, (
        "La cotización no llegó a la columna de adjuntos del tracker de quien "
        "hace el trabajo")


@pytest.mark.parametrize("persona", [
    "TERESA GARZA",          # del organigrama
    "PEDRO NUEVO INGRESO",   # nadie la conoce todavía
    "  angel salinas  ",     # capturada de cualquier manera
])
def test_la_orden_se_puede_mandar_a_cualquier_persona_con_su_adjunto(base, persona):
    """
    «A cualquier persona que se asigne»: el destino lo da `hoja_de_persona`, que
    no exige que la partición exista —quien no tenía tracker lo estrena— y el
    adjunto viaja igual.
    """
    respuesta = work_order.process_and_save_work_order(
        [_orden(programa=[_linea(responsable=persona)])], "PREWORK_ORDER")
    assert respuesta["success"] is True, respuesta.get("message")

    derivadas = [f for f in base.select("tasks")
                 if f.get("concepto", "").startswith("MONTAR TABLERO")]
    assert derivadas, f"{persona} no recibió la línea de programa"
    for tarea in derivadas:
        assert tarea["carpeta"] == COTIZACION, (
            f"{persona} recibió la tarea sin la cotización adjunta")


def test_la_cabecera_conserva_su_adjunto(base):
    """La fila de quien cotizó no cambia: esto añade, no mueve."""
    work_order.process_and_save_work_order([_orden()], "PREWORK_ORDER")

    (cabecera,) = _tareas_de(base, "ADMINISTRADOR")
    assert cabecera["carpeta"] == COTIZACION


def test_sin_documentos_la_tarea_derivada_no_trae_adjunto(base):
    work_order.process_and_save_work_order(
        [_orden(archivoUrl="")], "PREWORK_ORDER")

    (tarea,) = _tareas_de(base, "TERESA GARZA")
    assert not tarea["carpeta"]
