"""
Repositorio de `geo_prospectos`: el estado comercial de un establecimiento del DENUE.

Es la mitad mutable del módulo de prospección. La otra —el catálogo del INEGI,
20,957 establecimientos— vive en un SQLite de solo lectura dentro del bundle y
la lee `api/services/denue_repo.py`. Las dos mitades no se mezclan, y esa es la
decisión D2 del plan: el dato de terceros no entra a los respaldos de la empresa
y las 21,000 filas ajenas no se suben a Supabase solo para leerlas.

Aquí no hay cliente HTTP nuevo. Se usa el `DataEngine` que ya existe, así que la
misma clase corre contra Supabase (`PostgrestEngine`, `urllib` estándar, elegido
porque respeta el proxy HTTPS de este entorno) y contra `MemoryEngine` en las
pruebas, sin una línea distinta. R7 se cumple sin escribir nada nuevo.

Una sola escritura y un solo camino: `guardar` hace upsert por `denue_id`. No
hay `crear` aparte de `actualizar` porque **un establecimiento tiene un solo
estado comercial**; dos filas para el mismo negocio serían dos verdades sobre a
quién ya se llamó.
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from backend.core.engine import DataEngine
from backend.core.errors import BackendError, ErrorDeMotor
from backend.schemas.geo_prospecto import ProspectoRead, ProspectoWrite

TABLA = "geo_prospectos"
CLAVE_UPSERT = "denue_id"


class ProspectoNoEncontrado(BackendError):
    """No hay ninguna fila de `geo_prospectos` para ese establecimiento."""


def _ahora() -> str:
    return datetime.now(timezone.utc).isoformat()


class GeoProspectoRepository:
    """Acceso a `geo_prospectos` sobre cualquier `DataEngine`."""

    def __init__(self, engine: DataEngine):
        self.engine = engine

    # --- lectura ------------------------------------------------------

    def buscar(self, denue_id: str) -> Optional[Dict[str, Any]]:
        """La fila cruda, o `None`. Es la que decide si un guardado es alta."""
        filas = self.engine.select(TABLA, donde={CLAVE_UPSERT: str(denue_id or "").strip()})
        return filas[0] if filas else None

    def obtener(self, denue_id: str) -> ProspectoRead:
        fila = self.buscar(denue_id)
        if fila is None:
            raise ProspectoNoEncontrado(
                f"El establecimiento {denue_id!r} todavía no es un prospecto")
        return ProspectoRead.model_validate(fila)

    def listar(self, *, estado: Optional[str] = None,
               vendedor: Optional[str] = None) -> List[ProspectoRead]:
        """Los prospectos del panel. Sin filtros, todos los que ya tienen estado."""
        donde: Dict[str, Any] = {}
        if estado:
            donde["estado"] = str(estado).upper().strip()
        if vendedor:
            donde["vendedor"] = vendedor
        filas = self.engine.select(TABLA, donde=donde or None, orden="updated_at.desc")
        return [ProspectoRead.model_validate(f) for f in filas]

    # --- escritura ----------------------------------------------------

    def guardar(self, prospecto: ProspectoWrite) -> ProspectoRead:
        """
        Marca el estado comercial del establecimiento. Alta o cambio, mismo camino.

        `created_at` solo se escribe cuando la fila no existía. Reescribirlo en
        cada cambio de estado borraría el dato de cuándo entró el prospecto al
        embudo, que es lo único con lo que se puede medir cuánto tarda un
        negocio en pasar de NUEVO a COTIZANDO.

        `web_cache` no se toca nunca desde aquí: la escribe el job de
        enriquecimiento fuera de línea, y el upsert de PostgREST fusiona en vez
        de reemplazar, así que omitir la columna la conserva.
        """
        ahora = _ahora()
        previo = self.buscar(prospecto.establecimiento_id)

        fila: Dict[str, Any] = {
            CLAVE_UPSERT: prospecto.establecimiento_id,
            "estado": prospecto.estado,
            "vendedor": prospecto.vendedor,
            "nota": prospecto.nota,
            "updated_at": ahora,
        }
        if previo is None:
            fila["created_at"] = ahora

        guardadas = self.engine.upsert(TABLA, [fila], en_conflicto=CLAVE_UPSERT)
        if not guardadas:
            # PostgREST devuelve la fila porque `upsert` pide
            # `Prefer: return=representation`. Si llega vacío, el guardado no
            # está confirmado: mejor un error visible que un `IndexError` que
            # sale a pantalla como un 500 sin causa.
            raise ErrorDeMotor(f"El guardado en {TABLA} no devolvió la fila guardada")
        return ProspectoRead.model_validate(guardadas[0])
