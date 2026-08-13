"""
Router de `bug_tickets`, bajo `/api/v2` igual que `tasks`.

Cuatro rutas, un verbo cada una: crear, listar, mover de estatus, agregar
evidencia. A propósito no existe una quinta que reciba `descripcion` o
`evidencia` en un PATCH — es la garantía, a nivel de superficie de API, de
que ningún camino reescribe lo que ya se reportó.
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Dict, Optional

from fastapi import APIRouter, Body, Depends, HTTPException, Query
from pydantic import BaseModel, Field

from backend.core.engine import DataEngine, construir_engine
from backend.core.errors import BackendError, SinMotorConfigurado
from backend.repositories.tickets import TicketNoEncontrado, TicketRepository
from backend.schemas.ticket import TicketUpdate, TicketWrite

router = APIRouter(prefix="/api/v2", tags=["tickets"])


def obtener_repositorio() -> TicketRepository:
    """Dependencia: un repositorio por petición, con el motor que toque."""
    try:
        engine: DataEngine = construir_engine()
    except SinMotorConfigurado as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    return TicketRepository(engine)


class SolicitudTicket(BaseModel):
    ticket: TicketWrite
    reportado_por: str = Field(..., min_length=1)
    contexto: Optional[Dict[str, Any]] = None


class SolicitudEvidencia(BaseModel):
    """Mismo cuerpo que `/api/legacy/upload`: data URL, tipo y nombre."""

    data: str = Field(..., min_length=1)
    type: Optional[str] = None
    name: Optional[str] = None


@router.post("/tickets")
def crear_ticket(
    solicitud: SolicitudTicket = Body(...),
    repo: TicketRepository = Depends(obtener_repositorio),
) -> Dict[str, Any]:
    try:
        creado = repo.crear(solicitud.ticket, solicitud.reportado_por, solicitud.contexto)
    except BackendError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return {"success": True, "data": creado.model_dump(mode="json")}


@router.get("/tickets")
def listar_tickets(
    estatus: Optional[str] = Query(None),
    modulo: Optional[str] = Query(None),
    reportado_por: Optional[str] = Query(None),
    repo: TicketRepository = Depends(obtener_repositorio),
) -> Dict[str, Any]:
    tickets = repo.listar(estatus=estatus, modulo=modulo, reportado_por=reportado_por)
    return {
        "success": True,
        "data": [t.model_dump(mode="json") for t in tickets],
        "count": len(tickets),
    }


@router.patch("/tickets/{folio}")
def actualizar_ticket(
    folio: str,
    cambios: TicketUpdate = Body(...),
    repo: TicketRepository = Depends(obtener_repositorio),
) -> Dict[str, Any]:
    try:
        actualizado = repo.actualizar_estatus(folio, cambios)
    except TicketNoEncontrado as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    return {"success": True, "data": actualizado.model_dump(mode="json")}


@router.post("/tickets/{folio}/evidencia")
def agregar_evidencia(
    folio: str,
    solicitud: SolicitudEvidencia = Body(...),
    repo: TicketRepository = Depends(obtener_repositorio),
) -> Dict[str, Any]:
    """
    Sube el archivo (bucket privado, whitelist, tope de tamaño — ver
    `api/services/storage.subir_evidencia_ticket`) y lo agrega al ticket.
    No hay parámetro para reemplazar un adjunto existente: la única
    operación posible aquí es añadir uno nuevo.
    """
    from api.services import storage

    subida = storage.subir_evidencia_ticket(folio, solicitud.data, solicitud.type, solicitud.name)
    if not subida.get("success"):
        raise HTTPException(status_code=400, detail=subida.get("message") or "No se pudo subir la evidencia.")

    item = {
        "url": subida["fileUrl"],
        "tipo": subida["mime"],
        "sha256": subida["sha256"],
        "subido_en": datetime.now(timezone.utc).isoformat(),
    }
    try:
        actualizado = repo.agregar_evidencia(folio, item)
    except TicketNoEncontrado as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    return {"success": True, "data": actualizado.model_dump(mode="json")}
