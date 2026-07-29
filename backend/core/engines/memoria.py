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
}

# Valores por defecto reales. Importan porque una columna NOT NULL **con**
# default se puede omitir en un alta y una **sin** default no.
DEFAULTS: Dict[str, Dict[str, Any]] = {
    "tasks": {
        "id": "00000000-0000-0000-0000-000000000000",
        "folio_sintetico": False,
        "avance": 0,
        "status": "PENDIENTE",
        "created_at": "1970-01-01T00:00:00Z",
    },
}

# Columnas NOT NULL sin default: en un alta hay que darlas o la base aborta.
SIN_DEFAULT: Dict[str, tuple] = {
    tabla: tuple(c for c in columnas if c not in DEFAULTS.get(tabla, {}))
    for tabla, columnas in NO_NULOS.items()
}


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

        destino = self.datos.setdefault(tabla, [])
        indice = {f.get(en_conflicto): f for f in destino if f.get(en_conflicto) is not None}
        resultado: List[Dict[str, Any]] = []

        for fila in filas:
            clave = fila.get(en_conflicto)
            if clave is None:
                raise ErrorDeMotor(
                    f"Fila sin {en_conflicto}: el upsert no tiene con qué resolver el conflicto",
                    codigo="23502",
                )
            existente = indice.get(clave)
            if existente is None:
                self._validar_alta(tabla, fila)
                nueva = dict(DEFAULTS.get(tabla, {}))
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
        destino = self.datos.setdefault(tabla, [])
        nuevas = []
        for fila in filas:
            nueva = dict(DEFAULTS.get(tabla, {}))
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
