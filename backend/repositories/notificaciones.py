"""
Repositorio de `ticket_notificaciones`: los avisos que ve quien reportó un bug.

Un aviso es un **evento**, no un estado: un ticket que pasa por ABIERTO,
EN_REVISION y RESUELTO produce tres avisos, y cada uno se marca como leído por
separado. Por eso es una tabla aparte y no columnas dentro de `bug_tickets`.

Regla que gobierna todo este módulo: **notificar nunca puede tumbar la
operación que lo originó.** Si el aviso falla, el ticket ya se guardó y el
ticket es lo que importa. Es la misma decisión que ya toma
`tracker_store._enviar_webhook` con Make.com ("una falla no debe romper el
guardado"), y la razón por la que `crear_para_ticket` traga sus excepciones y
las registra en vez de propagarlas.
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Sequence

from backend.core.engine import DataEngine
from backend.schemas.notificacion import NotificacionRead, mensaje_de

TABLA = "ticket_notificaciones"


class NotificacionRepository:
    """Acceso a `ticket_notificaciones` sobre cualquier `DataEngine`."""

    def __init__(self, engine: DataEngine):
        self.engine = engine

    # --- escritura -------------------------------------------------------

    def crear_para_ticket(
        self,
        folio: Any,
        destinatario: Any,
        estatus: Any,
        actor: Any = None,
    ) -> Optional[NotificacionRead]:
        """
        Genera el aviso de un cambio de estatus. Devuelve `None` cuando no
        había nada que avisar, que **no** es un error.

        Se calla en tres casos, todos deliberados:

        * el estatus no tiene mensaje asociado (`mensaje_de` devuelve `None`);
        * no se sabe a quién avisar;
        * `actor` es la misma persona que reportó — quien mueve su propio
          ticket ya sabe lo que hizo, y avisárselo solo ensucia la campanita.

        Nunca lanza. Un fallo al escribir el aviso se registra y se traga: el
        ticket ya está guardado y perder el aviso es infinitamente preferible
        a perder el reporte.
        """
        quien = str(destinatario or "").strip()
        mensaje = mensaje_de(estatus)
        if not quien or not mensaje:
            return None
        if actor and str(actor).strip().upper() == quien.upper():
            return None

        fila: Dict[str, Any] = {
            "folio": str(folio or ""),
            "destinatario": quien,
            "estatus": str(estatus or "").upper().strip(),
            "mensaje": mensaje,
            "leida": False,
            "created_at": datetime.now(timezone.utc).isoformat(),
        }
        try:
            guardadas = self.engine.insertar(TABLA, [fila])
        except Exception as exc:  # noqa: BLE001 - ver docstring del módulo
            print(f"[notificaciones] no se pudo avisar de {folio!r} a {quien!r}: {exc}")
            return None
        return NotificacionRead.model_validate(guardadas[0])

    def marcar_leidas(self, destinatario: Any, ids: Optional[Sequence[str]] = None) -> int:
        """
        Marca avisos como leídos y devuelve cuántos cambió.

        Sin `ids`, marca todas las de esa persona — el botón "marcar todas".
        El filtro por `destinatario` se aplica **siempre**, también cuando
        vienen ids: así una petición con el id de otra persona no puede
        marcarle sus avisos.
        """
        quien = str(destinatario or "").strip()
        if not quien:
            return 0

        pendientes = [
            f for f in self.engine.select(TABLA, donde={"destinatario": quien})
            if not f.get("leida") and (ids is None or f.get("id") in set(ids))
        ]
        if not pendientes:
            return 0

        for fila in pendientes:
            fila["leida"] = True
        self.engine.upsert(TABLA, pendientes, en_conflicto="id")
        return len(pendientes)

    # --- lectura ---------------------------------------------------------

    def listar(self, destinatario: Any, solo_no_leidas: bool = False) -> List[NotificacionRead]:
        """Avisos de una persona, de la más reciente a la más vieja."""
        quien = str(destinatario or "").strip()
        if not quien:
            return []
        filas = self.engine.select(TABLA, donde={"destinatario": quien})
        if solo_no_leidas:
            filas = [f for f in filas if not f.get("leida")]
        filas.sort(key=lambda f: str(f.get("created_at") or ""), reverse=True)
        return [NotificacionRead.model_validate(f) for f in filas]

    def contar_no_leidas(self, destinatario: Any) -> int:
        """El número del globito de la campanita."""
        return len(self.listar(destinatario, solo_no_leidas=True))
