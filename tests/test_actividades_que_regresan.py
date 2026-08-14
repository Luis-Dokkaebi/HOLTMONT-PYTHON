"""
Una actividad terminada no vuelve a operativo porque otra persona guarde la suya.

Reporte del dueño (2026-08-14): "algunas actividades que ya habían terminado
regresaron activas o a operativo, y al tratar de cerrarlas al 100 % no se lo
permiten aunque vuelvan a subir todos los archivos".

La causa está en qué cuenta como "copia" de una actividad. La sincronización
bilateral (`tracker_store._sincronizar_copias`) propaga AVANCE, ESTATUS y
CUMPLIMIENTO a todas las filas que **comparten el folio**, porque para una
actividad asignada eso es exactamente lo que son: la misma actividad vista desde
la tabla de quien asigna y la de quien recibe.

El programa de una orden de trabajo rompe esa equivalencia.
`work_order.tareas_de_programa` estampa el folio de la **orden** en cada renglón
(`"FOLIO": cabecera.get("FOLIO", "")`), así que dos trabajos distintos, de dos
personas distintas, viajan con el mismo folio. Con la regla vieja:

1. Geraldine cerraba su renglón al 100 % y el de Miguel se archivaba solo, sin
   que él lo tocara ni subiera evidencia;
2. Miguel guardaba el suyo al 30 % y el de Geraldine, ya terminado, volvía a
   operativo con 30 %.

`campos_sincronizables` ya excluye las microtareas de papa caliente por la misma
razón —comparten folio y no son la misma actividad— y su docstring describe el
peligro palabra por palabra. Los renglones de programa no llevaban esa marca.

Lo que fija este archivo: la identidad de una copia es folio **+ CONCEPTO**. Las
copias de verdad lo comparten por construcción (`construir_espejo` lo copia tal
cual y `CAMPOS_BILATERALES` lo excluye a propósito para que no diverja); los
renglones de programa no.
"""

from __future__ import annotations

from typing import Any, Dict, List

import pytest

from api.services import sheets, tracker_store
from backend.core.engines.memoria import MemoryEngine
from backend.services.persistencia import PersistenciaTracker

FOLIO_ORDEN = "0042-ACME-EL"

CONCEPTO_GERALDINE = "Memoria de calculo [PROGRAMA: INGENIERIA]"
CONCEPTO_MIGUEL = "Montaje de tablero [PROGRAMA: EJECUCION]"


def _fila(n: int, hoja: str, folio: str, concepto: str, responsable: str,
          clave: str | None = None) -> Dict[str, Any]:
    return {
        "id": f"0000000{n}-0000-0000-0000-00000000000{n}",
        "dedupe_key": clave or f"{hoja}::{folio}",
        "folio": folio,
        "source_sheet": hoja,
        "concepto": concepto,
        "assignee_raw": responsable,
        "avance": 0.0,
        "status": "ASIGNADO",
        "folio_sintetico": False,
        "created_at": f"2026-08-0{n}T00:00:00Z",
    }


@pytest.fixture
def motor(monkeypatch):
    """La base con el programa de una orden repartido entre dos personas."""
    engine = MemoryEngine({
        "tasks": [
            _fila(1, "ADMINISTRADOR", FOLIO_ORDEN, "ORDEN DE TRABAJO ACME",
                  "MIGUEL GALLARDO", clave=FOLIO_ORDEN),
            _fila(2, "MIGUEL GALLARDO", FOLIO_ORDEN, CONCEPTO_MIGUEL, "MIGUEL GALLARDO"),
            _fila(3, "GERALDINE MARTINEZ", FOLIO_ORDEN, CONCEPTO_GERALDINE,
                  "GERALDINE MARTINEZ"),
        ],
        "quotes": [], "people": [], "plan_semanal": [],
        "task_involucrados": [], "system_log": [],
    })

    monkeypatch.setattr(tracker_store, "_persistencia",
                        lambda: PersistenciaTracker(engine))

    def leer(hoja):
        filas = [f for f in engine.select("tasks")
                 if str(f.get("source_sheet") or "").upper() == str(hoja).upper()]
        return sheets._valores_de_tareas(filas) or [
            ["FOLIO", "CONCEPTO", "INVOLUCRADOS", "AVANCE %", "STATUS"]]

    monkeypatch.setattr(tracker_store, "read_values", leer)
    return engine


def _guardar(hoja: str, concepto: str, responsable: str, avance: str,
             estatus: str, usuario: str = "") -> Dict[str, Any]:
    """Lo que manda la vista al guardar una fila del tracker."""
    return tracker_store.save_tracker_batch(hoja, [{
        "FOLIO": FOLIO_ORDEN, "CONCEPTO": concepto,
        "INVOLUCRADOS": responsable, "AVANCE": avance, "ESTATUS": estatus,
    }], usuario or hoja.replace(" ", "_"))


def _fila_de(motor: MemoryEngine, hoja: str) -> Dict[str, Any]:
    return next(f for f in motor.select("tasks")
                if f["source_sheet"] == hoja and f["folio"] == FOLIO_ORDEN)


def _archivadas(motor: MemoryEngine) -> List[str]:
    return sorted(f["source_sheet"] for f in motor.select("tasks")
                  if sheets._esta_archivada(f))


# ---------------------------------------------------------------------------
# El defecto reportado
# ---------------------------------------------------------------------------

def test_cerrar_mi_renglon_no_cierra_el_de_otra_persona(motor):
    """El 100 % de Geraldine no puede archivar el trabajo de Miguel."""
    assert _guardar("GERALDINE MARTINEZ", CONCEPTO_GERALDINE,
                    "GERALDINE MARTINEZ", "100", "HECHO")["success"] is True

    assert _archivadas(motor) == ["GERALDINE MARTINEZ"]
    miguel = _fila_de(motor, "MIGUEL GALLARDO")
    assert miguel["avance"] == 0.0
    assert miguel["status"] == "ASIGNADO"


def test_una_actividad_terminada_no_regresa_a_operativo(motor):
    """
    El caso exacto del reporte, en dos guardados.

    Geraldine termina lo suyo; después Miguel guarda **su** renglón al 30 % y la
    actividad de Geraldine tiene que seguir en TAREAS REALIZADAS.
    """
    _guardar("GERALDINE MARTINEZ", CONCEPTO_GERALDINE, "GERALDINE MARTINEZ",
             "100", "HECHO")
    _guardar("MIGUEL GALLARDO", CONCEPTO_MIGUEL, "MIGUEL GALLARDO",
             "30", "EN PROCESO")

    geraldine = _fila_de(motor, "GERALDINE MARTINEZ")
    assert geraldine["avance"] == 100.0, "el avance de Geraldine se pisó con el de Miguel"
    assert sheets._esta_archivada(geraldine) is True

    activas, historial, _ = tracker_store.read_rows("GERALDINE MARTINEZ")
    assert [a.get("CONCEPTO") for a in activas] == []
    assert [h.get("CONCEPTO") for h in historial] == [CONCEPTO_GERALDINE]


def test_el_renglon_de_cada_quien_conserva_su_propio_avance(motor):
    _guardar("MIGUEL GALLARDO", CONCEPTO_MIGUEL, "MIGUEL GALLARDO", "30", "EN PROCESO")

    assert _fila_de(motor, "MIGUEL GALLARDO")["avance"] == 30.0
    assert _fila_de(motor, "GERALDINE MARTINEZ")["avance"] == 0.0


# ---------------------------------------------------------------------------
# Lo que NO se puede romper: la bilateralidad de una actividad asignada
# ---------------------------------------------------------------------------

@pytest.fixture
def motor_asignacion(monkeypatch):
    """Una actividad asignada: misma actividad, dos tablas, mismo CONCEPTO."""
    engine = MemoryEngine({
        "tasks": [
            _fila(1, "ANTONIO SALAZAR", "AS-0001", "REVISAR PLANOS",
                  "GERALDINE MARTINEZ"),
            _fila(2, "GERALDINE MARTINEZ", "AS-0001", "REVISAR PLANOS",
                  "GERALDINE MARTINEZ"),
        ],
        "quotes": [], "people": [], "plan_semanal": [],
        "task_involucrados": [], "system_log": [],
    })
    monkeypatch.setattr(tracker_store, "_persistencia",
                        lambda: PersistenciaTracker(engine))

    def leer(hoja):
        filas = [f for f in engine.select("tasks")
                 if str(f.get("source_sheet") or "").upper() == str(hoja).upper()]
        return sheets._valores_de_tareas(filas) or [
            ["FOLIO", "CONCEPTO", "INVOLUCRADOS", "AVANCE %", "STATUS"]]

    monkeypatch.setattr(tracker_store, "read_values", leer)
    return engine


def test_el_100_de_quien_recibe_sigue_archivando_en_las_dos_tablas(motor_asignacion):
    """
    La regla 1 de `tests/test_asignacion_bilateral.py`, intacta.

    Es la mitad que el arreglo NO puede romper: una actividad asignada sí es la
    misma actividad en las dos tablas, y ahí el folio compartido significa lo
    que siempre significó.
    """
    res = tracker_store.save_tracker_batch("GERALDINE MARTINEZ", [{
        "FOLIO": "AS-0001", "CONCEPTO": "REVISAR PLANOS",
        "INVOLUCRADOS": "GERALDINE MARTINEZ", "AVANCE": "100", "ESTATUS": "HECHO",
    }], "GERALDINE_MARTINEZ")
    assert res["success"] is True

    hojas = sorted(f["source_sheet"] for f in motor_asignacion.select("tasks")
                   if sheets._esta_archivada(f))
    assert hojas == ["ANTONIO SALAZAR", "GERALDINE MARTINEZ"]


def test_sin_concepto_en_la_captura_se_usa_el_de_la_fila_guardada(motor_asignacion):
    """
    Un guardado parcial (sin CONCEPTO) no pierde la sincronización.

    La referencia sale entonces de la fila almacenada en la hoja de origen, que
    es la que el usuario tiene delante.
    """
    res = tracker_store.save_tracker_batch("GERALDINE MARTINEZ", [{
        "FOLIO": "AS-0001", "AVANCE": "100",
    }], "GERALDINE_MARTINEZ")
    assert res["success"] is True

    antonio = next(f for f in motor_asignacion.select("tasks")
                   if f["source_sheet"] == "ANTONIO SALAZAR")
    assert antonio["avance"] == 100.0
