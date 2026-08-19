"""
Contrato de `geo_prospectos`: el estado comercial de un establecimiento del DENUE.

Separado de `backend/schemas/ticket.py` y de `task.py` a propósito. Un prospecto
no es una actividad del tracker ni un bug: no tiene FOLIO, no se reparte entre
hojas y su única regla propia es la máquina de estados de abajo.

La clave es `denue_id`, el identificador del establecimiento en el catálogo del
INEGI. No hay clave propia porque no hace falta: **un establecimiento tiene un
solo estado comercial**. Dos filas para el mismo negocio serían dos verdades
distintas sobre a quién ya se llamó, que es justo lo que este módulo existe para
evitar.
"""

from __future__ import annotations

from datetime import datetime
from typing import Any, Optional

from pydantic import BaseModel, ConfigDict, Field, field_validator

# La máquina de estados del prospecto (plan de prospección §6.2). El orden es el
# del embudo comercial y se usa para saber qué es avanzar y qué es retroceder.
ESTADOS_VALIDOS: tuple = ("NUEVO", "CONTACTADO", "COTIZANDO", "DESCARTADO")

# `DESCARTADO` es el único del que se puede volver: un negocio descartado hoy
# puede reactivarse cuando cambie de dueño o de tamaño. `COTIZANDO` no es
# terminal porque la cotización puede caerse y el prospecto vuelve al embudo.
ESTADO_INICIAL: str = "NUEVO"

COLUMNAS_GEO_PROSPECTOS: tuple = (
    "denue_id", "estado", "vendedor", "nota",
    "web_cache", "web_cache_at", "created_at", "updated_at",
)


class ProspectoWrite(BaseModel):
    """
    Lo que manda el mapa al marcar un establecimiento.

    `extra="forbid"`: ni `web_cache` ni `created_at` se cuelan por aquí aunque
    el cliente reenvíe la fila completa en un round-trip ingenuo. La caché del
    sitio la escribe el job de enriquecimiento, no el navegador, y una fecha de
    alta que el cliente pueda mover deja de servir para auditar nada.
    """

    model_config = ConfigDict(extra="forbid")

    establecimiento_id: str = Field(..., min_length=1)
    estado: str = ESTADO_INICIAL
    vendedor: Optional[str] = None
    nota: Optional[str] = None

    @field_validator("estado", mode="before")
    @classmethod
    def _estado_valido(cls, valor: Any) -> str:
        """
        Un estado desconocido se rechaza; no se corrige a `NUEVO`.

        Degradar en silencio a `NUEVO` convertiría un error de tecleo del
        cliente en "este negocio nunca se ha contactado", que es una mentira
        sobre el trabajo que alguien ya hizo.
        """
        texto = str(valor if valor not in (None, "") else ESTADO_INICIAL).upper().strip()
        if texto not in ESTADOS_VALIDOS:
            raise ValueError(f"estado debe ser uno de {ESTADOS_VALIDOS}, llegó {valor!r}")
        return texto

    @field_validator("establecimiento_id", mode="before")
    @classmethod
    def _id_limpio(cls, valor: Any) -> str:
        return str(valor or "").strip()

    @field_validator("vendedor", "nota", mode="before")
    @classmethod
    def _texto_o_nulo(cls, valor: Any) -> Optional[str]:
        """Cadena vacía y nulo son lo mismo: "no se declaró"."""
        texto = str(valor or "").strip()
        return texto or None


class ProspectoRead(BaseModel):
    """Una fila de `geo_prospectos` tal como sale de la base."""

    model_config = ConfigDict(extra="allow")

    denue_id: Optional[str] = None
    estado: Optional[str] = None
    vendedor: Optional[str] = None
    nota: Optional[str] = None
    web_cache: Optional[str] = None
    web_cache_at: Optional[datetime] = None
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None
