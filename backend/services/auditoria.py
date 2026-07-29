"""
Auditoría en `system_log`: el port de `registrarLog()` de `CODIGO.js`.

`system_log` tiene 16.196 filas escritas desde Apps Script y **cero** desde el
backend Python (§1.11 del plan). Cada guardado, cada login y cada cambio de
fecha dejaba rastro mientras el sistema corría sobre GAS, y dejó de dejarlo al
migrar a FastAPI. Este módulo cierra ese hueco.

Dos reglas de diseño:

* **Registrar nunca puede tumbar la operación que se está auditando.** Si la
  base rechaza el log, se avisa por consola y el guardado sigue. Es el mismo
  criterio que `SupabaseSync.mirrorLog`, que envuelve todo en un try/catch.
* **El detalle se escribe igual que en GAS** (`"Update Task ID: ZA-0040 en
  JUANA MARIA RODRIGUEZ JUAREZ"`), para que las dos épocas de la bitácora se
  puedan leer y filtrar juntas.
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Optional, Sequence

from backend.core.engine import DataEngine, construir_engine

TABLA = "system_log"

# Tipos de acción que ya existen en la bitácora escrita por Apps Script. Se
# reutilizan tal cual en vez de inventar nuevos.
ACCION_LOGIN = "LOGIN"
ACCION_ACTUALIZAR = "ACTUALIZAR"
ACCION_CREAR = "CREAR"
ACCION_CAMBIO_FECHA = "CAMBIO_FECHA"


def _ahora_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _fila(usuario: Any, accion: str, detalles: Any) -> dict:
    return {
        "fecha_hora": _ahora_iso(),
        "usuario": str(usuario or "DESCONOCIDO").strip() or "DESCONOCIDO",
        "accion": str(accion or "").strip(),
        "detalles": str(detalles or "").strip(),
    }


def registrar(
    usuario: Any,
    accion: str,
    detalles: Any = "",
    *,
    engine: Optional[DataEngine] = None,
) -> bool:
    """
    Escribe una línea en `system_log`. Devuelve si se pudo.

    `id` no se manda: la columna es una identidad de Postgres y dejar que la
    genere la base es lo que evita colisiones entre invocaciones concurrentes
    de serverless.
    """
    return registrar_lote([_fila(usuario, accion, detalles)], engine=engine)


def registrar_lote(filas: Sequence[dict], *, engine: Optional[DataEngine] = None) -> bool:
    """
    Varias líneas en un solo INSERT.

    Un guardado del tracker puede tocar diez tareas; una petición HTTP por cada
    una convertiría la auditoría en la parte más lenta del guardado.
    """
    if not filas:
        return True
    try:
        motor = engine or construir_engine()
        motor.insertar(TABLA, list(filas))
        return True
    except Exception as exc:  # noqa: BLE001 - auditar no puede romper la operación auditada
        print(f"[auditoria] No se pudieron registrar {len(filas)} evento(s): {exc}")
        return False


def evento(usuario: Any, accion: str, detalles: Any = "") -> dict:
    """Construye una línea para acumularla y mandarla con `registrar_lote`."""
    return _fila(usuario, accion, detalles)


def detalle_tarea(folio: Any, hoja: Any, es_alta: bool = False) -> str:
    """Mismo texto que `registrarLog` en Apps Script, para no partir la bitácora."""
    verbo = "New Task ID" if es_alta else "Update Task ID"
    return f"{verbo}: {folio or '-'} en {hoja or '-'}"
