"""
El retiro de copias solo se dispara cuando el responsable cambia de verdad.

Incidente del 2026-08-07: un clic en "Guardar Todo" en el tracker de Sebastián
borró **24 filas** de los trackers de otras personas. `MG-0094` dejó de existir
en la tabla de Miguel Gallardo; `RR-0286` y `RR-0288` en la de Ramiro; `JM-0030`
en la de Jehu. Ninguno de ellos había dejado de ser responsable.

La cadena era esta:

1. `_retirar_copias_huerfanas` corre en **todo** guardado, cambie o no el
   responsable, y borra las copias del folio que vivan en hojas que no estén en
   la lista de responsables vigentes.
2. Esa lista son los **responsables** de la fila. En la tabla de Sebastián el
   responsable de todas sus filas es él mismo, así que la lista de hojas
   vigentes se reduce a la suya: `{"SEBASTIAN PADILLA"}`.
3. La hoja de Miguel no figuraba en esa lista —no porque Miguel dejara de ser
   responsable, sino porque nunca estuvo en la columna INVOLUCRADOS de la copia
   de Sebastián— y su fila se borró.
4. "Guardar Todo" manda la tabla entera, así que el paso 3 se repitió por cada
   una de las 15 filas.

No hace falta que el dato esté mal para que esto ocurra: pasa con los nombres
completos, tal como están guardados. Se comprobó contra la base —los 43 valores
distintos de `assignee_raw` son nombres completos, no hay ni una inicial— y el
borrado se reproduce igual.

El arreglo ataca el paso 1, que es la causa raíz: el retiro es la mitad de una
**reasignación**, y en un guardado que no toca el responsable no hay
reasignación que ejecutar. La comprobación ya existía —`cambia_el_responsable`,
que `_bloqueo_por_reasignacion` ya usa en la ruta de al lado— y su propio
docstring advierte del caso: *"Lo mismo aplica a 'Guardar todo', que reenvía la
tabla entera con el responsable intacto"*. Solo faltaba consultarla aquí.

El retiro sigue existiendo y sigue haciendo lo que el dueño definió: al
reasignar, la actividad se retira de la tabla de quien dejó de ser responsable.
Lo único que cambia es cuándo se dispara.
"""

from __future__ import annotations

from typing import Any, Dict, List

import pytest

from api.services import tracker_store
from backend.core.engines.memoria import MemoryEngine
from backend.services.persistencia import PersistenciaTracker

# Reproduce la tabla de Sebastián el día del incidente: actividades suyas y
# copias de actividades que nacieron en las tablas de otros. El responsable es
# su nombre completo, tal como está en la base — el incidente no dependía de
# que el dato estuviera mal.
FILAS = [
    ("MIGUEL GALLARDO", "MG-0094", "Arc Flash Hazard Analysis S0626-13"),
    ("SEBASTIAN PADILLA", "MG-0094", "Arc Flash Hazard Analysis S0626-13"),
    ("RAMIRO RODRIGUEZ", "RR-0286", "instalacion electrica A/C 11 y 22"),
    ("SEBASTIAN PADILLA", "RR-0286", "instalacion electrica A/C 11 y 22"),
    ("SEBASTIAN PADILLA", "SP-0014", "PRESUPUESTO PROYECTO HVAC"),
]


def _semilla() -> List[Dict[str, Any]]:
    return [
        {
            "id": f"0000000{n}-0000-0000-0000-00000000000{n}",
            "dedupe_key": f"{hoja}::{folio}",
            "folio": folio,
            "source_sheet": hoja,
            "concepto": concepto,
            "assignee_raw": "SEBASTIAN PADILLA",
            "avance": 0.0,
            "status": "ASIGNADO",
            "folio_sintetico": False,
            "created_at": f"2026-08-0{n + 1}T00:00:00Z",
        }
        for n, (hoja, folio, concepto) in enumerate(FILAS)
    ]


@pytest.fixture
def motor():
    return MemoryEngine({
        "tasks": _semilla(),
        "quotes": [], "people": [], "plan_semanal": [],
        "task_involucrados": [], "system_log": [],
    })


@pytest.fixture
def tracker(monkeypatch, motor):
    monkeypatch.setattr(tracker_store, "_persistencia", lambda: PersistenciaTracker(motor))
    monkeypatch.setattr(
        tracker_store, "read_values",
        lambda hoja: [["FOLIO", "CONCEPTO", "INVOLUCRADOS", "AVANCE", "ESTATUS"]],
    )
    return motor


def _hojas_de(motor, folio: str) -> List[str]:
    return sorted(f["source_sheet"] for f in motor.select("tasks") if f["folio"] == folio)


def _guardar_todo(avance: str = "0",
                  involucrados: str = "SEBASTIAN PADILLA") -> Dict[str, Any]:
    """Lo que manda la vista al pulsar 'Guardar Todo': la tabla entera."""
    return tracker_store.save_tracker_batch(
        "SEBASTIAN PADILLA",
        [{"FOLIO": folio, "CONCEPTO": concepto, "INVOLUCRADOS": involucrados,
          "AVANCE": avance, "ESTATUS": "ASIGNADO"}
         for hoja, folio, concepto in FILAS if hoja == "SEBASTIAN PADILLA"],
        username="SEBASTIAN_PADILLA",
    )


def test_guardar_todo_no_borra_las_filas_de_los_demas(tracker):
    """El incidente, reproducido: antes del arreglo esto dejaba 3 filas de 5."""
    claves_antes = {f["dedupe_key"] for f in tracker.select("tasks")}

    respuesta = _guardar_todo()

    assert respuesta["success"] is True, respuesta.get("message")
    claves_despues = {f["dedupe_key"] for f in tracker.select("tasks")}
    assert claves_antes - claves_despues == set(), (
        "un guardado que no cambia el responsable no puede borrar ninguna fila; "
        f"desaparecieron {sorted(claves_antes - claves_despues)}"
    )
    assert "MIGUEL GALLARDO" in _hojas_de(tracker, "MG-0094")
    assert "RAMIRO RODRIGUEZ" in _hojas_de(tracker, "RR-0286")


def test_editar_el_avance_tampoco_borra_nada(tracker):
    """El caso exacto del incidente: solo se tocó AVANCE."""
    _guardar_todo(avance="100")

    assert "MIGUEL GALLARDO" in _hojas_de(tracker, "MG-0094")
    assert [f["avance"] for f in tracker.select("tasks")
            if f["folio"] == "SP-0014"
            and f["source_sheet"] == "SEBASTIAN PADILLA"] == [100.0], (
        "el avance sí se guarda"
    )


def test_una_reasignacion_de_verdad_sigue_retirando_la_copia(tracker):
    """
    El arreglo no desactiva la regla, solo deja de dispararla sin motivo.

    Aquí Sebastián sí reasigna: quita a Miguel de INVOLUCRADOS y pone a Jaime.
    La copia de Miguel se retira, que es la decisión del dueño de siempre.
    """
    tracker.upsert("tasks", [{
        "id": "0000000a-0000-0000-0000-00000000000a",
        "dedupe_key": "MIGUEL GALLARDO::SP-0014", "folio": "SP-0014",
        "source_sheet": "MIGUEL GALLARDO", "concepto": "PRESUPUESTO PROYECTO HVAC",
        "assignee_raw": "MIGUEL GALLARDO", "avance": 0.0, "status": "ASIGNADO",
        "folio_sintetico": False, "created_at": "2026-08-09T00:00:00Z",
    }], en_conflicto="dedupe_key")
    assert "MIGUEL GALLARDO" in _hojas_de(tracker, "SP-0014")

    respuesta = tracker_store.save_tracker_batch(
        "SEBASTIAN PADILLA",
        [{"FOLIO": "SP-0014", "CONCEPTO": "PRESUPUESTO PROYECTO HVAC",
          "INVOLUCRADOS": "JAIME OLIVO", "AVANCE": "0", "ESTATUS": "ASIGNADO"}],
        username="SEBASTIAN_PADILLA",
    )

    assert respuesta["success"] is True, respuesta.get("message")
    assert "MIGUEL GALLARDO" not in _hojas_de(tracker, "SP-0014"), (
        "quien deja de ser responsable sí pierde su copia"
    )
    assert "JAIME OLIVO" in _hojas_de(tracker, "SP-0014"), (
        "y el nuevo responsable la recibe"
    )
