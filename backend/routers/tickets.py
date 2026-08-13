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
from backend.core.errors import BackendError, ErrorDeMotor, SinMotorConfigurado
from backend.repositories.tickets import TicketNoEncontrado, TicketRepository
from backend.schemas.ticket import TicketUpdate, TicketWrite

router = APIRouter(prefix="/api/v2", tags=["tickets"])

# PostgREST no encuentra la tabla. `PGRST205` es el código actual ("Could not
# find the table in the schema cache"); `42P01` es el `undefined_table` de
# Postgres, que asoma cuando el error viene de la base y no del router de
# PostgREST.
CODIGOS_TABLA_FALTANTE = frozenset({"PGRST205", "PGRST202", "42P01"})

MENSAJE_TABLA_FALTANTE = (
    "El sistema de tickets todavía no está instalado en la base de datos: falta "
    "crear la tabla `bug_tickets`. Aplicar el DDL de docs/DDL_PENDIENTE.sql §5."
)

MENSAJE_MOTOR_CAIDO = (
    "No se pudo consultar el sistema de tickets. Vuelve a intentarlo; si sigue "
    "fallando, avisa al equipo."
)


def obtener_repositorio() -> TicketRepository:
    """Dependencia: un repositorio por petición, con el motor que toque."""
    try:
        engine: DataEngine = construir_engine()
    except SinMotorConfigurado as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    return TicketRepository(engine)


def _es_tabla_faltante(exc: BackendError) -> bool:
    if not isinstance(exc, ErrorDeMotor):
        return False
    if exc.codigo in CODIGOS_TABLA_FALTANTE:
        return True
    # PostgREST no siempre manda `code` en el cuerpo. El 404 basta como señal:
    # la ruta la arma el motor, no el cliente, así que un "no existe" solo
    # puede ser la tabla.
    return "respondió 404" in str(exc)


def _fallo_de_motor(exc: BackendError) -> HTTPException:
    """
    Traduce un fallo del motor a una respuesta que le sirva a quien la lee.

    El detalle interno se registra pero **no viaja al cliente**: el 2026-08-13
    el dueño intentó reportar un bug y recibió en pantalla
    `PostgREST GET bug_tickets?select=folio&offset=0&limit=1000 respondió 404`,
    que no le dice qué hacer y además expone la consulta. Se separan las dos
    causas porque piden acciones distintas: falta el DDL (503, accionable) o
    la base no responde (502, reintentar).
    """
    print(f"[tickets] fallo del motor: {exc}")
    if _es_tabla_faltante(exc):
        return HTTPException(status_code=503, detail=MENSAJE_TABLA_FALTANTE)
    return HTTPException(status_code=502, detail=MENSAJE_MOTOR_CAIDO)


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
    except ErrorDeMotor as exc:
        raise _fallo_de_motor(exc) from exc
    except BackendError as exc:
        # Lo que sí es culpa de la petición: p. ej. sin usuario en sesión.
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return {"success": True, "data": creado.model_dump(mode="json")}


@router.get("/tickets")
def listar_tickets(
    estatus: Optional[str] = Query(None),
    modulo: Optional[str] = Query(None),
    reportado_por: Optional[str] = Query(None),
    repo: TicketRepository = Depends(obtener_repositorio),
) -> Dict[str, Any]:
    try:
        tickets = repo.listar(estatus=estatus, modulo=modulo, reportado_por=reportado_por)
    except BackendError as exc:
        raise _fallo_de_motor(exc) from exc
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
    except BackendError as exc:
        raise _fallo_de_motor(exc) from exc
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
    except BackendError as exc:
        raise _fallo_de_motor(exc) from exc
    return {"success": True, "data": actualizado.model_dump(mode="json")}
