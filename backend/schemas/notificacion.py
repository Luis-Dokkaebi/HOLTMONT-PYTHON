"""
Avisos a quien reportó un bug: qué se le dice y cuándo.

Los textos son fijos y viven aquí, no en la base ni en el frontend. Es una
decisión, no una limitación: quien reporta un bug espera una respuesta del
sistema, no un campo libre que alguien pueda dejar en blanco o llenar con
prisa un martes. Cambiarlos exige desplegar, y eso es correcto — son la voz
del sistema hacia el equipo.

El canal es dentro de la plataforma, no correo. La razón está medida: de las
41 cuentas del organigrama, **solo 6 tienen correo registrado**. Un aviso por
correo no le llegaría a 35 personas, y peor, fallaría en silencio.

Lo que sí es libre es la `nota`: la que escribe quien resuelve al mover el
ticket. Va **junto** al texto fijo, nunca en su lugar — el texto fijo dice en
qué estado quedó el reporte, y la nota dice qué pasó con ese bug en concreto.
Un ticket movido sin nota sigue avisando exactamente como antes.
"""

from __future__ import annotations

from datetime import datetime
from typing import Any, Dict, Optional

from pydantic import BaseModel, ConfigDict, Field, field_validator

COLUMNAS_NOTIFICACIONES: tuple = (
    "id", "folio", "destinatario", "estatus", "mensaje", "nota", "leida", "created_at",
)

# NOT NULL sin DEFAULT: hay que darlas en cada alta.
OBLIGATORIAS_AL_INSERTAR: frozenset = frozenset(
    {"folio", "destinatario", "estatus", "mensaje"}
)

# El texto de cada aviso, por el estatus al que llegó el ticket.
#
# `ABIERTO` es el acuse de recibo: se emite al crear el ticket, para que quien
# reportó sepa que llegó y con qué folio referirse a él.
MENSAJES: Dict[str, str] = {
    "ABIERTO": (
        "Recibimos tu reporte. Lo revisaremos y te avisaremos de cualquier avance."
    ),
    "EN_REVISION": (
        "Estamos trabajando en tu problema, te avisaremos cuando quede resuelto."
    ),
    "RESUELTO": (
        "Tu reporte quedó resuelto. Si el problema se repite, vuelve a reportarlo."
    ),
    "CERRADO": (
        "Tu reporte se cerró. Si crees que sigue pendiente, vuelve a reportarlo."
    ),
    "NO_ES_BUG": (
        "Revisamos tu reporte y el sistema está funcionando como debe. "
        "Si necesitas ayuda con el proceso, búscanos."
    ),
}


def mensaje_de(estatus: Any) -> Optional[str]:
    """
    Texto del aviso para ese estatus, o `None` si no hay ninguno que dar.

    Devolver `None` es una respuesta válida y no un error: significa "este
    cambio no amerita molestar a nadie". Es lo que permite añadir estatus
    nuevos sin que el sistema invente un aviso vacío.
    """
    return MENSAJES.get(str(estatus or "").upper().strip())


def nota_normalizada(nota: Any) -> Optional[str]:
    """
    La nota tal como debe guardarse, o `None` si no hay nota que dar.

    Espacios en blanco no son una nota: guardarlos deja un renglón vacío en la
    campanita, que se lee como si el sistema hubiera querido decir algo y se
    hubiera quedado callado.
    """
    limpia = str(nota or "").strip()
    return limpia or None


class NotificacionRead(BaseModel):
    """Un aviso tal como sale de la base."""

    model_config = ConfigDict(extra="allow")

    id: Optional[str] = None
    folio: Optional[str] = None
    destinatario: Optional[str] = None
    estatus: Optional[str] = None
    mensaje: Optional[str] = None
    # Lo que escribió quien resolvió, si escribió algo. Nulo en los avisos que
    # se movieron sin nota y en los que vienen de una base con el DDL viejo.
    nota: Optional[str] = None
    leida: bool = False
    created_at: Optional[datetime] = None

    @field_validator("leida", mode="before")
    @classmethod
    def _leida_nunca_nula(cls, valor: Any) -> Any:
        """`leida` es NOT NULL DEFAULT false; un nulo se trata como no leída,
        que es el lado seguro: peor es esconderle un aviso a alguien."""
        return bool(valor)


class MarcarLeidas(BaseModel):
    """Cuerpo de la petición para marcar avisos como leídos."""

    model_config = ConfigDict(extra="forbid")

    destinatario: str = Field(..., min_length=1)
    # Vacío o ausente = todas las de esa persona. Es lo que hace el botón
    # "marcar todas como leídas" de la campanita.
    ids: Optional[list] = None
