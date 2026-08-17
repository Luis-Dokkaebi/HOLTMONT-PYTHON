"""
Repositorio de `bug_tickets`: alta, listado y las dos únicas mutaciones que
existen después de creado un ticket — mover de estatus y agregar evidencia.

No hay un tercer camino. `actualizar_estatus` nunca acepta `descripcion` ni
`evidencia`; `agregar_evidencia` nunca acepta reemplazar el arreglo, solo
extenderlo.

Eso cubre a la aplicación, que es lo que este módulo controla. **No cubre a
quien tenga la clave de servicio**: se midió contra el proyecto real el
2026-08-13 que `service_role` sobrescribe (`PUT` con `x-upsert`) y borra
objetos del bucket pese a las políticas, porque tiene BYPASSRLS. Storage no
ofrece object-lock, así que no hay forma de impedirlo.

Por eso `evidencia[].sha256` no es un adorno: es el mecanismo que convierte
una alteración en algo **detectable**. Ver `verificar_evidencia`.
"""

from __future__ import annotations

import re
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from backend.core.engine import DataEngine
from backend.core.errors import BackendError, ErrorDeMotor
from backend.schemas.ticket import (
    ESTATUS_TERMINALES,
    TicketRead,
    TicketUpdate,
    TicketWrite,
)

TABLA = "bug_tickets"
CLAVE_UPSERT = "folio"

FORMATO_DE_FOLIO = re.compile(r"^BUG-(\d+)$")

# `23505` es `unique_violation`; PostgREST lo devuelve como 409. Dos altas
# simultáneas calculan el mismo folio, así que el segundo insert rebota: se
# recalcula y se reintenta en vez de devolverle el fallo a quien reporta.
CODIGOS_FOLIO_OCUPADO = frozenset({"23505"})
INTENTOS_DE_ALTA = 5


class TicketNoEncontrado(BackendError):
    """No hay ningún `bug_tickets` con ese folio."""


def _ahora() -> str:
    return datetime.now(timezone.utc).isoformat()


def _es_folio_ocupado(exc: ErrorDeMotor) -> bool:
    """La base rechazó el insert porque ese folio ya existe."""
    return exc.codigo in CODIGOS_FOLIO_OCUPADO or exc.estado == 409


class TicketRepository:
    """Acceso a `bug_tickets` sobre cualquier `DataEngine`."""

    def __init__(self, engine: DataEngine):
        self.engine = engine
        # Los avisos a quien reportó viven en otra tabla y en otro
        # repositorio. Se compone aquí, y no se inyecta por el constructor,
        # porque avisar no es opcional para el negocio: un ticket que cambia
        # de estatus sin avisar es la queja que originó esta funcionalidad.
        from backend.repositories.notificaciones import NotificacionRepository

        self.notificaciones = NotificacionRepository(engine)

    # --- identidad --------------------------------------------------------

    def _siguiente_folio(self) -> str:
        """
        `BUG-0001`, `BUG-0002`... a partir del folio **más alto** que ya existe.

        Contar las filas era lo que hacía antes, y bloqueó el sistema entero:
        medido contra la base real el 2026-08-17, `bug_tickets` tenía una sola
        fila y su folio era `BUG-0002` (de `BUG-0001` no quedaba rastro). El
        conteo daba `1 + 1 = BUG-0002`, que ya estaba tomado, y como `folio` es
        UNIQUE cada alta moría con un `23505`. No era intermitente: todo el
        equipo llevaba días sin poder reportar un bug, y reintentar —lo único
        que sugería el mensaje en pantalla— daba siempre el mismo folio.

        Con el máximo, un hueco en la numeración deja de importar: un ticket
        borrado, una migración parcial o una fila cargada a mano ya no vuelven
        a chocar. Los folios que no tienen la forma `BUG-\\d+` se ignoran en vez
        de tumbar el alta.

        Sigue sin haber candado, igual que `DB_SITIOS.ID_SITIO`
        (docs/DDL_PENDIENTE.sql §2): dos altas en el mismo instante calculan el
        mismo número. Eso lo resuelve `crear` reintentando sobre la UNIQUE, que
        es la que convierte la colisión en un error visible en vez de una
        fusión silenciosa de dos tickets en una sola fila.
        """
        mayor = 0
        for fila in self.engine.select(TABLA, columnas=["folio"]):
            reconocido = FORMATO_DE_FOLIO.match(str(fila.get("folio") or "").strip().upper())
            if reconocido:
                mayor = max(mayor, int(reconocido.group(1)))
        return f"BUG-{mayor + 1:04d}"

    def _fila_completa(self, folio: str) -> Dict[str, Any]:
        filas = self.engine.select(TABLA, donde={"folio": folio})
        if not filas:
            raise TicketNoEncontrado(f"No existe el ticket {folio!r}")
        return filas[0]

    # --- lectura ------------------------------------------------------------

    def obtener(self, folio: str) -> TicketRead:
        return TicketRead.model_validate(self._fila_completa(folio))

    def listar(
        self,
        *,
        estatus: Optional[str] = None,
        modulo: Optional[str] = None,
        reportado_por: Optional[str] = None,
    ) -> List[TicketRead]:
        donde: Dict[str, Any] = {}
        if estatus:
            donde["estatus"] = estatus
        if modulo:
            donde["modulo"] = modulo
        if reportado_por:
            donde["reportado_por"] = reportado_por
        filas = self.engine.select(TABLA, donde=donde or None)
        return [TicketRead.model_validate(f) for f in filas]

    # --- escritura ------------------------------------------------------

    def crear(
        self,
        ticket: TicketWrite,
        reportado_por: str,
        contexto: Optional[Dict[str, Any]] = None,
    ) -> TicketRead:
        """
        Da de alta el ticket. `reportado_por` viene de la sesión, nunca del
        cuerpo de `TicketWrite` — es la misma razón por la que `tasks` pone
        `source_sheet` en el servidor y no deja que el cliente lo mande.

        Si el folio calculado ya está tomado, se recalcula y se reintenta: la
        UNIQUE de `folio` señala la colisión y el alta se resuelve sola en vez
        de rebotarle a quien reporta un error que no puede arreglar.
        """
        if not str(reportado_por or "").strip():
            raise BackendError("No se puede reportar un ticket sin usuario en sesión.")

        ahora = _ahora()
        fila: Dict[str, Any] = {
            "folio": "",
            "reportado_por": reportado_por,
            "modulo": ticket.modulo,
            "descripcion": ticket.descripcion,
            "pasos_reproducir": ticket.pasos_reproducir,
            "severidad": ticket.severidad,
            "estatus": "ABIERTO",
            "evidencia": [],
            "contexto": contexto or {},
            "created_at": ahora,
            "updated_at": ahora,
        }

        guardadas: List[Dict[str, Any]] = []
        for intento in range(INTENTOS_DE_ALTA):
            fila["folio"] = self._siguiente_folio()
            try:
                guardadas = self.engine.insertar(TABLA, [fila])
            except ErrorDeMotor as exc:
                if not _es_folio_ocupado(exc) or intento == INTENTOS_DE_ALTA - 1:
                    raise
                continue
            break

        if not guardadas:
            # PostgREST devuelve la fila porque `insertar` pide
            # `Prefer: return=representation`. Si aun así llega vacío, el alta
            # no está confirmada: mejor un error visible que un `IndexError`
            # que sale a pantalla como un 500 sin causa.
            raise ErrorDeMotor(f"El alta en {TABLA} no devolvió la fila guardada")
        creado = TicketRead.model_validate(guardadas[0])
        # Acuse de recibo: que quien reportó sepa que llegó y con qué folio
        # referirse a él. Sin `actor`, porque aquí el reportante SÍ debe
        # recibirlo aunque sea quien lo creó.
        self.notificaciones.crear_para_ticket(creado.folio, creado.reportado_por, "ABIERTO")
        return creado

    def actualizar_estatus(self, folio: str, cambios: TicketUpdate) -> TicketRead:
        """
        Mueve el ticket de estatus. Parte de la fila completa que ya está en
        la base y solo pisa los campos permitidos — igual que
        `_completar_obligatorias` en `backend/repositories/tasks.py`, para
        que el upsert nunca mande a Postgres una columna NOT NULL en blanco.
        """
        fila = dict(self._fila_completa(folio))
        fila["estatus"] = cambios.estatus
        fila["resolucion_notas"] = cambios.resolucion_notas
        if cambios.estatus in ESTATUS_TERMINALES:
            fila["resuelto_por"] = cambios.resuelto_por
            fila["resuelto_en"] = _ahora()
        fila["updated_at"] = _ahora()

        guardadas = self.engine.upsert(TABLA, [fila], en_conflicto=CLAVE_UPSERT)
        if not guardadas:
            raise ErrorDeMotor(f"El cambio de estatus en {TABLA} no devolvió la fila guardada")
        actualizado = TicketRead.model_validate(guardadas[0])
        # Avisar a quien reportó, no a quien resolvió: `actor` evita que
        # soporte se notifique a sí mismo al mover un ticket propio.
        #
        # La nota de resolución viaja con el aviso: es lo único que le dice a
        # quien reportó qué pasó con *su* bug. Hasta ahora se guardaba en la
        # fila del ticket, donde solo la veía soporte en su panel.
        self.notificaciones.crear_para_ticket(
            actualizado.folio, actualizado.reportado_por, cambios.estatus,
            actor=cambios.resuelto_por,
            nota=cambios.resolucion_notas,
        )
        return actualizado

    def agregar_evidencia(self, folio: str, item: Dict[str, Any]) -> TicketRead:
        """
        Agrega un adjunto ya subido a Storage al arreglo `evidencia`.

        No existe `reemplazar_evidencia` ni un parámetro que permita pisar el
        arreglo existente: la única operación posible sobre `evidencia` es
        `list.append`.
        """
        fila = dict(self._fila_completa(folio))
        evidencia_actual = list(fila.get("evidencia") or [])
        evidencia_actual.append(item)
        fila["evidencia"] = evidencia_actual
        fila["updated_at"] = _ahora()

        guardadas = self.engine.upsert(TABLA, [fila], en_conflicto=CLAVE_UPSERT)
        if not guardadas:
            raise ErrorDeMotor(f"El alta de evidencia en {TABLA} no devolvió la fila guardada")
        return TicketRead.model_validate(guardadas[0])
