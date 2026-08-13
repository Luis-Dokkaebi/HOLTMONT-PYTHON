"""
Contrato de `bug_tickets`: qué puede mandar quien reporta, qué puede tocar
quien resuelve, y qué no puede tocar nadie una vez guardado.

Separado de `backend/schemas/task.py` a propósito: un ticket no es una
actividad del tracker, no hereda sus fallbacks (`PENDIENTE`, `NO`) y su
regla central es distinta — `descripcion` y `evidencia` son de solo lectura
después del alta, no solo columnas técnicas como `id` o `dedupe_key`.
"""

from __future__ import annotations

from datetime import datetime
from typing import Any, Dict, List, Optional

from pydantic import BaseModel, ConfigDict, Field, field_validator

SEVERIDADES: tuple = ("BAJA", "MEDIA", "ALTA", "CRITICA")
ESTATUS_VALIDOS: tuple = ("ABIERTO", "EN_REVISION", "RESUELTO", "CERRADO", "NO_ES_BUG")

# Una vez en uno de estos, el ticket lleva "resuelto_por"/"resuelto_en".
ESTATUS_TERMINALES: frozenset = frozenset({"RESUELTO", "CERRADO", "NO_ES_BUG"})

COLUMNAS_BUG_TICKETS: tuple = (
    "id", "folio", "reportado_por", "modulo", "descripcion", "pasos_reproducir",
    "severidad", "estatus", "evidencia", "contexto",
    "resuelto_por", "resuelto_en", "resolucion_notas",
    "created_at", "updated_at",
)

# NOT NULL sin DEFAULT en el esquema (docs/DDL_PENDIENTE.sql): hay que darlas
# en cada alta o Postgres aborta con 23502.
OBLIGATORIAS_AL_INSERTAR: frozenset = frozenset(
    {"folio", "reportado_por", "modulo", "descripcion"}
)


def _texto_normalizado(valor: Any, opciones: tuple, campo: str) -> str:
    v = str(valor or "").upper().strip()
    if v not in opciones:
        raise ValueError(f"{campo} debe ser uno de {opciones}, llegó {valor!r}")
    return v


class TicketWrite(BaseModel):
    """
    Lo que manda quien reporta. `extra="forbid"`: ni `estatus` ni `evidencia`
    se cuelan por aquí, aunque el cliente los reenvíe en un round-trip
    ingenuo — para eso están `TicketUpdate` y el endpoint de evidencia,
    que son las únicas dos vías de mutación después del alta.
    """

    model_config = ConfigDict(extra="forbid")

    modulo: str = Field(..., min_length=1)
    descripcion: str = Field(..., min_length=1)
    pasos_reproducir: Optional[str] = None
    severidad: str = "MEDIA"

    @field_validator("severidad", mode="before")
    @classmethod
    def _severidad_valida(cls, valor: Any) -> str:
        return _texto_normalizado(valor if valor not in (None, "") else "MEDIA", SEVERIDADES, "severidad")


class TicketUpdate(BaseModel):
    """
    Lo único que puede tocar quien resuelve un ticket: a dónde se mueve y por
    qué. Ni `descripcion` ni `evidencia` son campos de este modelo — no es
    una omisión, es la garantía de que un PATCH nunca puede reescribir lo que
    ya se reportó.
    """

    model_config = ConfigDict(extra="forbid")

    estatus: str
    resolucion_notas: Optional[str] = None
    resuelto_por: Optional[str] = None

    @field_validator("estatus", mode="before")
    @classmethod
    def _estatus_valido(cls, valor: Any) -> str:
        return _texto_normalizado(valor, ESTATUS_VALIDOS, "estatus")


class EvidenciaItem(BaseModel):
    """Un adjunto ya subido a Storage. Se agrega al arreglo; nunca lo reemplaza."""

    model_config = ConfigDict(extra="forbid")

    url: str = Field(..., min_length=1)
    tipo: str = Field(..., min_length=1)
    sha256: Optional[str] = None
    subido_en: Optional[datetime] = None


class TicketRead(BaseModel):
    """Una fila de `bug_tickets` tal como sale de la base."""

    model_config = ConfigDict(extra="allow")

    id: Optional[str] = None
    folio: Optional[str] = None
    reportado_por: Optional[str] = None
    modulo: Optional[str] = None
    descripcion: Optional[str] = None
    pasos_reproducir: Optional[str] = None
    severidad: Optional[str] = None
    estatus: Optional[str] = None
    evidencia: List[Dict[str, Any]] = Field(default_factory=list)
    contexto: Optional[Dict[str, Any]] = None
    resuelto_por: Optional[str] = None
    resuelto_en: Optional[datetime] = None
    resolucion_notas: Optional[str] = None
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None

    @field_validator("evidencia", mode="before")
    @classmethod
    def _evidencia_nunca_nula(cls, valor: Any) -> Any:
        """`evidencia` es NOT NULL DEFAULT '[]' en el esquema; nulo no debería
        llegar nunca, pero degradar a lista vacía es más seguro que tronar la
        lectura de un ticket por una fila vieja sin este campo poblado."""
        return valor or []
