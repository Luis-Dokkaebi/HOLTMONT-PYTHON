"""
Guardado de una Pre Work Order (`/api/savePPC`).

La versión anterior de esta prueba comprobaba el **modo mock**: llamaba a
`api_save_ppc_data` y luego leía las hojas en memoria de `GSheetsManager`. Eso
verificaba justo lo que estaba roto, porque en el despliegue no hay
`credentials.json` y ese diccionario en memoria muere con la invocación: la
prueba pasaba y el usuario perdía su captura.

Ahora se comprueba lo que importa: que la work order aterrice en la base —la
tarea en la partición de su responsable, los materiales y la mano de obra en
sus tablas, el folio en `work_orders` y el renglón del índice en
`plan_semanal`—. Corre sobre `MemoryEngine`, sin base de datos.
"""

from __future__ import annotations

import os
import sys

import pytest

sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from api.main import SavePPCRequest, api_save_ppc_data  # noqa: E402
from backend.core.engines.memoria import MemoryEngine  # noqa: E402

PAYLOAD = [{
    "cliente": "TEST CLIENT",
    "especialidad": "TEST DEPT",
    "concepto": "Test Concept",
    "responsable": "JAIME OLIVO",
    "prioridad": "Alta",
    "fechaRespuesta": "01/01/2025",
    "materiales": [
        {"quantity": "10", "unit": "pza", "description": "Test Material",
         "cost": "100", "total": "1000"}
    ],
    "manoObra": [
        {"category": "Test Labor", "salary": "1000", "personnel": "1",
         "weeks": "1", "total": "1000"}
    ],
}]


@pytest.fixture
def motor(monkeypatch):
    """Un `MemoryEngine` compartido por todo el flujo de guardado."""
    engine = MemoryEngine({
        "tasks": [],
        "people": [{"id": "p-1", "nombre": "JAIME OLIVO"}],
        "plan_semanal": [],
        "work_orders": [],
        "wo_materiales": [],
        "wo_mano_obra": [],
        "task_involucrados": [],
        "system_log": [],
    })
    monkeypatch.setenv("BACKEND_ENGINE", "memoria")
    monkeypatch.setattr("backend.core.engine.construir_engine", lambda *a, **k: engine)
    monkeypatch.setattr("api.services.work_order._engine", lambda: engine)
    monkeypatch.setattr("api.services.work_order._hay_base", lambda: True)

    import backend.services.persistencia as persistencia

    original = persistencia.PersistenciaTracker.__init__

    def init(self, engine_=None):
        original(self, engine)

    monkeypatch.setattr(persistencia.PersistenciaTracker, "__init__", init)
    return engine


def test_la_work_order_se_guarda_en_la_base(motor):
    respuesta = api_save_ppc_data(SavePPCRequest(payload=PAYLOAD, activeUser="TEST_USER"))

    assert respuesta["success"] is True, respuesta.get("message")
    assert len(respuesta["ids"]) == 1
    folio = respuesta["ids"][0]

    tareas = motor.select("tasks")
    assert len(tareas) == 1, "la tarea debe existir una sola vez (folio PPC- es global)"
    assert tareas[0]["concepto"] == "Test Concept"
    # Lo que pide el encargo: cae en la tabla de su responsable, no en una
    # partición "PPCV3" que nadie lee.
    assert tareas[0]["source_sheet"] == "JAIME OLIVO"
    assert tareas[0]["folio"] == folio

    indice = motor.select("plan_semanal", donde={"source_sheet": "PPCV3"})
    assert [f["task_folio"] for f in indice] == [folio], "debe quedar indexada en el PPC maestro"

    assert [f["folio"] for f in motor.select("work_orders")] == [folio]

    materiales = motor.select("wo_materiales")
    assert len(materiales) == 1
    assert materiales[0]["descripcion"] == "Test Material"
    assert materiales[0]["folio"] == folio
    # El formulario manda texto; la columna es numérica.
    assert materiales[0]["cantidad"] == 10.0
    assert materiales[0]["total"] == 1000.0

    mano_obra = motor.select("wo_mano_obra")
    assert len(mano_obra) == 1
    assert mano_obra[0]["categoria"] == "Test Labor"

    involucrados = motor.select("task_involucrados")
    assert [f["raw_name"] for f in involucrados] == ["JAIME OLIVO"]
    assert involucrados[0]["person_id"] == "p-1"

    acciones = [f["accion"] for f in motor.select("system_log")]
    assert "CREAR" in acciones


def test_un_fallo_de_escritura_no_se_reporta_como_exito(motor, monkeypatch):
    """La lección de la Fase 0: nunca `success: true` sin haber escrito."""
    from backend.core.errors import ErrorDeMotor

    def revienta(*_args, **_kwargs):
        raise ErrorDeMotor("la base rechazó el lote")

    monkeypatch.setattr(motor, "upsert", revienta)

    respuesta = api_save_ppc_data(SavePPCRequest(payload=PAYLOAD, activeUser="TEST_USER"))

    assert respuesta["success"] is False
    assert "rechazó el lote" in respuesta["message"]


if __name__ == "__main__":
    pytest.main([__file__])
