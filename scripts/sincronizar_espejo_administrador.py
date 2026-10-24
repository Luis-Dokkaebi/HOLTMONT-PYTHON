#!/usr/bin/env python3
"""
Pone al día el avance de la hoja espejo `ADMINISTRADOR` con su cotización.

`ADMINISTRADOR` es la hoja de control del original: recibe una copia de las
actividades para que dirección las vea todas juntas, sin login propio
(`CREDENCIALES.md`, "Conservados a propósito"). En la migración esas copias se
importaron con el avance que tenían ese día y **nunca se volvieron a
sincronizar**, así que la cotización siguió avanzando y su espejo se quedó
congelado.

El efecto que se ve: actividades terminadas que siguen apareciendo como activas.
El reparto entre activo y `TAREAS REALIZADAS` se calcula al leer, a partir del
avance; con el espejo en 0 o en 99 y la cotización en 100, la copia nunca baja.

Medido el 2026-08: de 1.701 filas espejo, 506 tienen cotización, 226 difieren en
avance y **214 van por detrás, todas con su cotización al 100 %**.

Qué hace y qué NO hace:

  * Copia el `avance` de la cotización a su fila espejo. Nada más.
  * **Solo cuando el espejo va por detrás.** Si el espejo va por delante (12
    casos) no se toca: ahí el espejo sabe algo que la cotización no, y elegir
    por él sería inventar.
  * No crea ni borra filas. No toca `quotes`, que es la fuente.

La fuente de verdad es la cotización, no el espejo: `quotes` es donde el
vendedor trabaja y `ADMINISTRADOR` es una copia para mirar.

Uso:

    python scripts/sincronizar_espejo_administrador.py              # simula
    python scripts/sincronizar_espejo_administrador.py --aplicar    # escribe

Antes de escribir deja `respaldo_espejo_<fecha>.json` con el valor anterior de
cada fila, para poder deshacerlo.

Requiere SUPABASE_URL y SUPABASE_KEY, o DATABASE_URL (lee `.env` de la raíz).
"""

from __future__ import annotations

import argparse
import json
import pathlib
import sys
from datetime import datetime
from typing import Any, Dict, List, Sequence, Tuple

RAIZ = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(RAIZ))

from scripts.migrar_perfiles import cargar_env  # noqa: E402

HOJA_ESPEJO = "ADMINISTRADOR"


def _avance(fila: Dict[str, Any]) -> float:
    """El avance como número; lo que no se pueda leer cuenta como 0."""
    try:
        return float(fila.get("avance") or 0)
    except (TypeError, ValueError):
        return 0.0


def filas_a_sincronizar(espejo: Sequence[Dict[str, Any]],
                        cotizaciones: Sequence[Dict[str, Any]],
                        ) -> List[Tuple[Dict[str, Any], float]]:
    """
    Las filas espejo que van por detrás de su cotización, con su avance nuevo.

    Función pura sobre las dos listas para que la suite la ejercite sin tocar la
    base (R7). Devuelve `(fila_espejo, avance_de_la_cotizacion)`.
    """
    por_folio = {str(c.get("folio")): c for c in cotizaciones}

    pendientes: List[Tuple[Dict[str, Any], float]] = []
    for fila in espejo:
        if str(fila.get("source_sheet") or "") != HOJA_ESPEJO:
            continue

        cotizacion = por_folio.get(str(fila.get("folio")))
        if cotizacion is None:
            continue

        actual, fuente = _avance(fila), _avance(cotizacion)
        # Solo hacia adelante: si el espejo va por delante, se respeta.
        if fuente > actual:
            pendientes.append((fila, fuente))

    return pendientes


def _resumen(pendientes: Sequence[Tuple[Dict[str, Any], float]]) -> Dict[str, int]:
    from api.services.tracker_rules import is_progress_complete_pct

    return {
        "total": len(pendientes),
        "quedan_archivadas": sum(1 for _, nuevo in pendientes
                                 if is_progress_complete_pct(nuevo)),
    }


def main() -> int:
    parser = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--aplicar", action="store_true",
                        help="Escribe en la base. Sin esta bandera solo informa.")
    args = parser.parse_args()

    cargar_env()

    from backend.core.engine import construir_engine

    engine = construir_engine()
    print(f"motor: {engine.nombre}")

    tareas = engine.select("tasks")
    cotizaciones = engine.select("quotes")
    espejo = [f for f in tareas if str(f.get("source_sheet") or "") == HOJA_ESPEJO]
    print(f"  {len(espejo)} fila(s) en la hoja espejo `{HOJA_ESPEJO}`")

    pendientes = filas_a_sincronizar(tareas, cotizaciones)
    datos = _resumen(pendientes)
    print(f"  {datos['total']} van por detrás de su cotización")
    print(f"  {datos['quedan_archivadas']} pasarían a TAREAS REALIZADAS al ponerse al día")

    if not pendientes:
        print("\nNada que sincronizar.")
        return 0

    print("\n  ejemplos:")
    for fila, nuevo in pendientes[:8]:
        print(f"    {str(fila.get('folio')):<14} {_avance(fila):>6} -> {nuevo}")

    if not args.aplicar:
        print("\nSimulación. Nada se escribió.")
        print("Vuelve a correrlo con --aplicar cuando quieras aplicarlo.")
        return 0

    respaldo = RAIZ / f"respaldo_espejo_{datetime.now():%Y%m%d_%H%M%S}.json"
    respaldo.write_text(json.dumps(
        [{"id": f.get("id"), "folio": f.get("folio"), "avance_anterior": f.get("avance")}
         for f, _ in pendientes], indent=2, default=str), encoding="utf-8")
    print(f"\nrespaldo del valor anterior: {respaldo.name}")

    # Se manda la fila COMPLETA, no `{id, avance}`: `upsert` en PostgREST es
    # `INSERT ... ON CONFLICT`, y `tasks` tiene cuatro columnas NOT NULL sin
    # default (`folio`, `dedupe_key`, `concepto`, `source_sheet`). Con un
    # upsert parcial el INSERT no valida y responde 400 sin escribir nada.
    # Las demás columnas se reescriben con el valor que ya tenían.
    for fila, nuevo in pendientes:
        engine.upsert("tasks", [{**fila, "avance": nuevo}], en_conflicto="id")

    print(f"{len(pendientes)} fila(s) sincronizadas.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
