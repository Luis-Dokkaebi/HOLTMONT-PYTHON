"""
Router de `tasks` sobre la capa relacional.

Va bajo `/api/v2` y **no** sustituye a ningún endpoint existente: `/api/data` y
`/api/legacy/...` siguen exactamente igual. El sistema está en uso diario y el
corte se hace al final y a propósito (docs/PLAN_BACKEND_PYTHON.md §2, Fase 7).

La forma de la respuesta imita la del contrato actual (`{success, data,
history, headers}`) para que el día del corte `api_service.js` pueda reapuntar
sin tocar `index.html`.
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional

from fastapi import APIRouter, Body, Depends, HTTPException, Query
from pydantic import BaseModel, Field

from backend.core.engine import DataEngine, construir_engine
from backend.core.errors import BackendError, EscrituraDeshabilitada, SinMotorConfigurado
from backend.repositories.tasks import TaskRepository
from backend.schemas.task import TaskWrite

router = APIRouter(prefix="/api/v2", tags=["tasks"])


def obtener_repositorio() -> TaskRepository:
    """Dependencia: un repositorio por petición, con el motor que toque."""
    try:
        engine: DataEngine = construir_engine()
    except SinMotorConfigurado as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    return TaskRepository(engine)


class LoteDeTareas(BaseModel):
    sheetName: str = Field(..., min_length=1)
    tasks: List[TaskWrite]
    username: Optional[str] = ""


@router.get("/tasks")
def listar_tareas(
    sheet: str = Query(..., description="Nombre de la hoja (tolerante a mayúsculas y espacios)"),
    repo: TaskRepository = Depends(obtener_repositorio),
) -> Dict[str, Any]:
    """
    Tareas de una hoja, con tipos y ya separadas en activas e historial.

    La separación es calculada (avance al 100 %, estatus terminal o
    CUMPLIMIENTO = SI), no la posición de la fila respecto a un separador.
    """
    try:
        activas, archivadas = repo.particionar(sheet)
    except BackendError as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc

    return {
        "success": True,
        "sheet": repo.resolver_hoja(sheet),
        "data": [t.model_dump(mode="json") for t in activas],
        "history": [t.model_dump(mode="json") for t in archivadas],
        "count": len(activas) + len(archivadas),
    }


@router.post("/tasks/batch")
def guardar_lote(
    lote: LoteDeTareas = Body(...),
    repo: TaskRepository = Depends(obtener_repositorio),
) -> Dict[str, Any]:
    """
    Guarda un lote de tareas en una transacción.

    Falla ruidosamente si la escritura está deshabilitada: la lección de la
    Fase 0 es que un `{success: true}` que no persiste nada es peor que un
    error, porque el frontend limpia el borrador y el usuario cree que guardó.
    """
    try:
        guardadas = repo.guardar_lote(lote.sheetName, lote.tasks)
    except EscrituraDeshabilitada as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    except BackendError as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc

    return {
        "success": True,
        "message": f"{len(guardadas)} tarea(s) guardada(s)",
        "data": [t.model_dump(mode="json") for t in guardadas],
    }
