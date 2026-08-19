"""
Motor en memoria: el doble de pruebas.

Existe para que la suite del repositorio corra **sin base de datos**, que es
uno de los entregables de la Fase 1. No es un modo de producción: no lo elige
la detección automática, hay que pedirlo con `BACKEND_ENGINE=memoria`.

Reproduce a propósito los tres comportamientos de Postgres de los que depende
la lógica y que un `dict` ingenuo se saltaría:

  * el upsert por clave única **fusiona** en vez de reemplazar la fila;
  * una columna `NOT NULL` rechaza el nulo con el código `23502`, que es el
    error real con el que tropezó la normalización de estatus;
  * la transacción revierte si algo falla dentro del contexto.
"""

from __future__ import annotations

import copy
import uuid
from contextlib import contextmanager
from typing import Any, Dict, Iterator, List, Optional, Sequence

from backend.core.errors import ErrorDeMotor

# Restricciones leídas del esquema real que publica PostgREST, reproducidas
# aquí para que las pruebas fallen igual que la base.
#
# `tasks` tiene **nueve** columnas NOT NULL, no solo `status` como decía el
# documento de partida. `quotes.estatus` sí admite nulo.
NO_NULOS: Dict[str, tuple] = {
    "tasks": (
        "id", "folio", "dedupe_key", "folio_sintetico", "concepto",
        "avance", "status", "source_sheet", "created_at",
    ),
    "quotes": ("folio",),
    "bug_tickets": (
        "id", "folio", "reportado_por", "modulo", "descripcion",
        "severidad", "estatus", "evidencia", "created_at", "updated_at",
    ),
    "ticket_notificaciones": (
        "id", "folio", "destinatario", "estatus", "mensaje", "leida", "created_at",
    ),
    # `geo_prospectos` (docs/DDL_PENDIENTE.sql §8). `vendedor`, `nota` y las dos
    # columnas de caché web admiten nulo: un prospecto recién marcado en el mapa
    # todavía no tiene dueño ni notas.
    "geo_prospectos": ("denue_id", "estado", "created_at", "updated_at"),
}

# Valores por defecto reales. Importan porque una columna NOT NULL **con**
# default se puede omitir en un alta y una **sin** default no.
#
# Un valor invocable se llama en cada alta, que es lo que hace falta para
# imitar a `gen_random_uuid()`. Con un UUID fijo, todas las filas de una tabla
# compartían `id`: inofensivo mientras el upsert use otra clave (`tasks` usa
# `dedupe_key`), pero `ticket_notificaciones` upserta por `id` y marcar un
# aviso como leído marcaba los de todo el mundo. El doble tiene que fallar
# donde falla la base, no donde no.
DEFAULTS: Dict[str, Dict[str, Any]] = {
    "tasks": {
        "id": lambda: str(uuid.uuid4()),
        "folio_sintetico": False,
        "avance": 0,
        "status": "PENDIENTE",
        "created_at": "1970-01-01T00:00:00Z",
    },
    "bug_tickets": {
        "id": lambda: str(uuid.uuid4()),
        "severidad": "MEDIA",
        "estatus": "ABIERTO",
        "evidencia": [],
        "created_at": "1970-01-01T00:00:00Z",
        "updated_at": "1970-01-01T00:00:00Z",
    },
    "ticket_notificaciones": {
        "id": lambda: str(uuid.uuid4()),
        "leida": False,
        "created_at": "1970-01-01T00:00:00Z",
    },
    # `denue_id` NO lleva default: es la PRIMARY KEY y la trae el catálogo del
    # INEGI, no la base. `estado` tampoco, aunque la aplicación siempre lo
    # mande: el DDL lo declara NOT NULL sin DEFAULT y el doble tiene que
    # rechazar el nulo donde lo rechazaría Postgres.
    "geo_prospectos": {
        "created_at": "1970-01-01T00:00:00Z",
        "updated_at": "1970-01-01T00:00:00Z",
    },
}

# Columnas NOT NULL sin default: en un alta hay que darlas o la base aborta.
SIN_DEFAULT: Dict[str, tuple] = {
    tabla: tuple(c for c in columnas if c not in DEFAULTS.get(tabla, {}))
    for tabla, columnas in NO_NULOS.items()
}


def _con_defaults(tabla: str) -> Dict[str, Any]:
    """Defaults de una tabla, resolviendo los invocables (ver DEFAULTS)."""
    return {c: (v() if callable(v) else v) for c, v in DEFAULTS.get(tabla, {}).items()}


class MemoryEngine:
    """Implementación de `DataEngine` sobre diccionarios."""

    nombre = "memoria"
    soporta_transacciones = True

    def __init__(self, datos: Optional[Dict[str, List[Dict[str, Any]]]] = None):
        self.datos: Dict[str, List[Dict[str, Any]]] = copy.deepcopy(datos or {})
        self._respaldo: Optional[Dict[str, List[Dict[str, Any]]]] = None

    # --- operaciones ---------------------------------------------------

    def select(
        self,
        tabla: str,
        *,
        columnas: Optional[Sequence[str]] = None,
        donde: Optional[Dict[str, Any]] = None,
        donde_en: Optional[Dict[str, Sequence[Any]]] = None,
        orden: Optional[str] = None,
        limite: Optional[int] = None,
    ) -> List[Dict[str, Any]]:
        filas = [copy.deepcopy(f) for f in self.datos.get(tabla, [])]

        for col, val in (donde or {}).items():
            filas = [f for f in filas if f.get(col) == val]
        for col, valores in (donde_en or {}).items():
            permitidos = set(valores)
            filas = [f for f in filas if f.get(col) in permitidos]

        if orden:
            columna, _, sentido = orden.partition(".")
            filas.sort(
                key=lambda f: (f.get(columna) is None, f.get(columna)),
                reverse=sentido.lower().startswith("desc"),
            )
        if limite is not None:
            filas = filas[:limite]
        if columnas:
            filas = [{c: f.get(c) for c in columnas} for f in filas]
        return filas

    def upsert(
        self,
        tabla: str,
        filas: Sequence[Dict[str, Any]],
        *,
        en_conflicto: str,
    ) -> List[Dict[str, Any]]:
        if not filas:
            return []
        self._validar_no_nulos(tabla, filas)

        # `en_conflicto` acepta clave compuesta separada por comas, igual que el
        # `on_conflict` de PostgREST: `quotes` la usa (`folio,source_sheet`)
        # porque la misma cotización vive en la tabla de quien la reparte y en
        # la de quien la recibe. `tasks` sigue con una sola (`dedupe_key`).
        columnas_clave = [c.strip() for c in str(en_conflicto).split(",") if c.strip()]

        def clave_de(fila: Dict[str, Any]) -> Optional[tuple]:
            valores = tuple(fila.get(c) for c in columnas_clave)
            return None if any(v is None for v in valores) else valores

        destino = self.datos.setdefault(tabla, [])
        indice = {clave_de(f): f for f in destino if clave_de(f) is not None}
        resultado: List[Dict[str, Any]] = []

        for fila in filas:
            clave = clave_de(fila)
            if clave is None:
                raise ErrorDeMotor(
                    f"Fila sin {en_conflicto}: el upsert no tiene con qué resolver el conflicto",
                    codigo="23502",
                )
            existente = indice.get(clave)
            if existente is None:
                self._validar_alta(tabla, fila)
                nueva = _con_defaults(tabla)
                nueva.update(copy.deepcopy(dict(fila)))
                destino.append(nueva)
                indice[clave] = nueva
                resultado.append(copy.deepcopy(nueva))
            else:
                # merge-duplicates: solo se tocan las columnas enviadas.
                existente.update(copy.deepcopy(dict(fila)))
                resultado.append(copy.deepcopy(existente))
        return resultado

    def insertar(self, tabla: str, filas: Sequence[Dict[str, Any]]) -> List[Dict[str, Any]]:
        if not filas:
            return []
        self._validar_no_nulos(tabla, filas)
        # Toda fila de un `insertar()` es, por definición, un alta: a
        # diferencia de `upsert`, aquí no hay "ya existía" que la exima de
        # traer las columnas NOT NULL sin default. Antes solo `upsert`
        # llamaba a `_validar_alta`, así que una tabla que solo usara
        # `insertar` (como `bug_tickets`) nunca veía este 23502 en pruebas
        # aunque la base real sí lo hubiera lanzado.
        for fila in filas:
            self._validar_alta(tabla, fila)
        destino = self.datos.setdefault(tabla, [])
        nuevas = []
        for fila in filas:
            nueva = _con_defaults(tabla)
            nueva.update(copy.deepcopy(dict(fila)))
            destino.append(nueva)
            nuevas.append(copy.deepcopy(nueva))
        return nuevas

    def borrar(self, tabla: str, donde: Dict[str, Any]) -> None:
        if not donde:
            raise ErrorDeMotor(f"DELETE sobre {tabla} sin filtros: se aborta por seguridad")
        self.datos[tabla] = [
            f for f in self.datos.get(tabla, [])
            if any(f.get(col) != val for col, val in donde.items())
        ]

    def _validar_alta(self, tabla: str, fila: Dict[str, Any]) -> None:
        """Un INSERT sin una columna NOT NULL y sin default aborta con 23502."""
        faltan = [c for c in SIN_DEFAULT.get(tabla, ()) if c not in fila]
        if faltan:
            raise ErrorDeMotor(
                f'null value in column "{faltan[0]}" of relation "{tabla}" '
                f"violates not-null constraint",
                codigo="23502",
            )

    def _validar_no_nulos(self, tabla: str, filas: Sequence[Dict[str, Any]]) -> None:
        for columna in NO_NULOS.get(tabla, ()):
            for fila in filas:
                if columna in fila and fila[columna] is None:
                    raise ErrorDeMotor(
                        f'null value in column "{columna}" of relation "{tabla}" '
                        f"violates not-null constraint",
                        codigo="23502",
                    )

    @contextmanager
    def transaccion(self) -> Iterator["MemoryEngine"]:
        if self._respaldo is not None:  # anidada: la externa manda
            yield self
            return
        self._respaldo = copy.deepcopy(self.datos)
        try:
            yield self
        except Exception:
            self.datos = self._respaldo
            raise
        finally:
            self._respaldo = None
