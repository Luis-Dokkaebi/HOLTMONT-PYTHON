"""
Traza ejecutable del flujo de papa caliente, de punta a punta.

No es una prueba unitaria (esas viven en `tests/`): es la **evidencia** de que
el flujo completo hace lo que dice la documentación, corriendo el mismo camino
que usa la aplicación —`/api/legacy/saveTrackerBatch` -> `tracker_store.
save_tracker_batch`— contra el motor en memoria, e imprimiendo el estado real de
la base después de cada acción.

Se corre a mano:

    ./venv/bin/python verification/verify_papa_caliente.py            # texto
    ./venv/bin/python verification/verify_papa_caliente.py --json     # traza

La salida JSON es la que alimenta el reporte visual del flujo. Nada aquí toca
la base de producción: el motor es `MemoryEngine`, igual que en la suite.
"""

from __future__ import annotations

import json
import os
import sys
from contextlib import contextmanager
from typing import Any, Dict, Iterator, List, Optional

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from api.services import sheets, tracker_store  # noqa: E402
from api.services import tracker_rules as rules  # noqa: E402
from backend.core.engines.memoria import MemoryEngine  # noqa: E402
from backend.services.persistencia import PersistenciaTracker  # noqa: E402

MAESTRA = rules.SALES_MASTER_SHEET          # ANTONIA_VENTAS
TONITA = "ANTONIA_VENTAS"                   # el username que reparte
FOLIO = "AV-3250"
MIGUEL = "MIGUEL GALLARDO"
ROLANDO = "ROLANDO MORENO"


# ----------------------------------------------------------------------
# Base de arranque: una cotización de Toñita y dos trabajadores con hoja
# ----------------------------------------------------------------------

def _motor() -> MemoryEngine:
    return MemoryEngine({
        "quotes": [{
            "folio": FOLIO,
            "source_sheet": MAESTRA,
            "cliente": "ACME",
            "concepto": "COTIZAR NAVE",
            "vendedor_raw": "TERESA GARZA",
            "avance": 0.0,
            "estatus": "EN PROCESO",
            "map_cot": "",
            "proceso_log": "",
        }],
        # Los trabajadores necesitan hoja existente: `resolve_worker_sheet`
        # comprueba que la partición tenga filas antes de delegar ahí.
        "tasks": [
            _tarea_semilla("MG-0001", MIGUEL),
            _tarea_semilla("RM-0001", ROLANDO),
        ],
        "people": [
            {"id": "p-1", "nombre": MIGUEL},
            {"id": "p-2", "nombre": ROLANDO},
        ],
        "plan_semanal": [],
        "task_involucrados": [],
        "system_log": [],
    })


def _tarea_semilla(folio: str, hoja: str) -> Dict[str, Any]:
    return {
        "id": f"0000-{folio}",
        "dedupe_key": f"{hoja}::{folio}",
        "folio": folio,
        "folio_sintetico": False,
        "source_sheet": hoja,
        "concepto": "TAREA PREVIA",
        "assignee_raw": hoja,
        "avance": 0.0,
        "status": "ASIGNADO",
        "created_at": "2026-08-01T00:00:00Z",
    }


@contextmanager
def _conectado(motor: MemoryEngine) -> Iterator[None]:
    """
    Apunta el tracker al motor en memoria —lectura y escritura— y lo devuelve
    como estaba al salir.

    La restauración no es cortesía: este módulo también se ejecuta desde la
    suite (`tests/test_flujo_papa_caliente_e2e.py`), y dejar `read_values`
    parcheado contaminaría las pruebas que corran después en el mismo proceso.
    """
    originales = (tracker_store._persistencia, tracker_store.read_values)
    tracker_store._persistencia = lambda: PersistenciaTracker(motor)

    def leer(hoja: str) -> List[List[Any]]:
        clave = sheets._clave_hoja(hoja)
        cotizaciones = [f for f in motor.select("quotes")
                        if sheets._clave_hoja(f.get("source_sheet")) == clave]
        if cotizaciones:
            return sheets._valores_de_cotizaciones(cotizaciones) or []
        tareas = [f for f in motor.select("tasks")
                  if sheets._clave_hoja(f.get("source_sheet")) == clave]
        if tareas:
            return sheets._valores_de_tareas(tareas) or []
        return []

    tracker_store.read_values = leer
    try:
        yield
    finally:
        tracker_store._persistencia, tracker_store.read_values = originales


# ----------------------------------------------------------------------
# Lecturas del estado real de la base
# ----------------------------------------------------------------------

def _cotizacion(motor: MemoryEngine, hoja: str = MAESTRA) -> Dict[str, Any]:
    for fila in motor.select("quotes"):
        if fila.get("folio") == FOLIO and sheets._clave_hoja(fila.get("source_sheet")) == sheets._clave_hoja(hoja):
            return fila
    return {}


def _microtareas(motor: MemoryEngine) -> List[Dict[str, Any]]:
    return sorted(
        [f for f in motor.select("tasks") if f.get("folio") == FOLIO],
        key=lambda f: str(f.get("source_sheet")),
    )


def _log(motor: MemoryEngine) -> List[Dict[str, Any]]:
    return rules.parse_proceso_log(_cotizacion(motor).get("proceso_log"))


def _foto(motor: MemoryEngine, titulo: str, detalle: str,
          extra: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    """El estado completo tras un paso, tal como está en la base."""
    maestra = _cotizacion(motor)
    return {
        "titulo": titulo,
        "detalle": detalle,
        "maestra": {
            "folio": maestra.get("folio"),
            "concepto": maestra.get("concepto"),
            "avance": maestra.get("avance"),
            "estatus": maestra.get("estatus"),
            "map_cot": maestra.get("map_cot") or "",
        },
        "proceso_log": _log(motor),
        "microtareas": [{
            "hoja": f.get("source_sheet"),
            "dedupe_key": f.get("dedupe_key"),
            "concepto": f.get("concepto"),
            "estatus": f.get("status"),
            "avance": f.get("avance"),
            "comentarios": f.get("comentarios") or "",
        } for f in _microtareas(motor)],
        **(extra or {}),
    }


# ----------------------------------------------------------------------
# El recorrido
# ----------------------------------------------------------------------

def recorrer() -> Dict[str, Any]:
    motor = _motor()
    with _conectado(motor):
        return _recorrido(motor)


def _recorrido(motor: MemoryEngine) -> Dict[str, Any]:
    pasos: List[Dict[str, Any]] = []

    # 0. Punto de partida --------------------------------------------------
    pasos.append(_foto(
        motor, "0 · Antes de delegar",
        f"{FOLIO} vive solo en {MAESTRA}: sin PROCESO_LOG, sin MAP COT y sin "
        f"ninguna microtarea en la hoja de nadie."))

    # 1. Toñita delega la fase CD a dos personas ---------------------------
    respuesta = tracker_store.save_tracker_batch(MAESTRA, [{
        "FOLIO": FOLIO,
        "CONCEPTO": "COTIZAR NAVE",
        "CLIENTE": "ACME",
        "_assignToWorker": [MIGUEL, ROLANDO],
        "_assignStep": "CD",
    }], username=TONITA)
    pasos.append(_foto(
        motor, "1 · Toñita delega la fase CD a Miguel y a Rolando",
        "Una sola llamada a `saveTrackerBatch`. `apply_hot_potato` abre una "
        "entrada IN_PROGRESS por persona, escribe el MAP COT y crea una fila en "
        "la hoja propia de cada trabajador, con la fase marcada en el CONCEPTO.",
        {"respuesta": respuesta}))

    # 2. Intento de saltar a la fase siguiente con CD abierta --------------
    bloqueo = tracker_store.save_tracker_batch(MAESTRA, [{
        "FOLIO": FOLIO,
        "CONCEPTO": "COTIZAR NAVE",
        "_assignToWorker": ["TERESA GARZA"],
        "_assignStep": "EP",
    }], username=TONITA)
    pasos.append(_foto(
        motor, "2 · Intento de delegar EP con CD todavía abierta",
        "El proceso es una secuencia. `bloqueo_de_fase` lanza `FaseEnCurso`, "
        "`save_tracker_batch` responde el motivo y **no escribe nada**: la foto "
        "de la base es idéntica a la del paso 1.",
        {"respuesta": bloqueo}))

    # 3. Miguel cierra su parte -------------------------------------------
    cierre_miguel = tracker_store.save_tracker_batch(MIGUEL, [{
        "FOLIO": FOLIO,
        "CONCEPTO": f"COTIZAR NAVE [{rules.phase_label('CD')}]",
        "AVANCE": "100",
        "ESTATUS": "HECHO",
    }], username=MIGUEL)
    pasos.append(_foto(
        motor, "3 · Miguel cierra su microtarea al 100 %",
        "Reverse sync: la maestra se entera por el PROCESO_LOG (Miguel pasa a "
        "DONE) pero **no** hereda AVANCE ni ESTATUS. CD sigue en 🔴 porque "
        "Rolando no ha terminado.",
        {"respuesta": cierre_miguel}))

    # 4. Rolando cierra la suya -------------------------------------------
    cierre_rolando = tracker_store.save_tracker_batch(ROLANDO, [{
        "FOLIO": FOLIO,
        "CONCEPTO": f"COTIZAR NAVE [{rules.phase_label('CD')}]",
        "AVANCE": "100",
        "ESTATUS": "HECHO",
    }], username=ROLANDO)
    pasos.append(_foto(
        motor, "4 · Rolando cierra la suya: la fase se pinta verde",
        "Ahora **todas** las entradas de CD están en DONE, así que "
        "`build_map_cot` pinta 🟢 CD. La cotización sigue viva: su AVANCE y su "
        "ESTATUS no se movieron.",
        {"respuesta": cierre_rolando}))

    # 5. Con CD cerrada, EP ya se puede delegar ----------------------------
    ep = tracker_store.save_tracker_batch(MAESTRA, [{
        "FOLIO": FOLIO,
        "CONCEPTO": "COTIZAR NAVE",
        "_assignToWorker": [MIGUEL],
        "_assignStep": "EP",
    }], username=TONITA)
    pasos.append(_foto(
        motor, "5 · Cerrada CD, la siguiente fase ya se delega",
        "Mismo intento que fracasó en el paso 2, ahora permitido. La papa pasa "
        "a la siguiente mano.",
        {"respuesta": ep}))

    return {
        "pasos": pasos,
        "invariantes": _invariantes(motor),
        "auditoria": [
            {"accion": e.get("accion"), "detalle": e.get("detalle"),
             "usuario": e.get("usuario")}
            for e in motor.select("system_log")
        ],
    }


def _invariantes(motor: MemoryEngine) -> List[Dict[str, Any]]:
    """Las cinco propiedades que el flujo promete, comprobadas contra la base."""
    maestra = _cotizacion(motor)
    micro = _microtareas(motor)
    claves = [f.get("dedupe_key") for f in micro]
    conceptos = [f.get("concepto") for f in micro]

    from api.services import asignacion

    comprobaciones = [
        (
            "Cada copia tiene identidad propia por hoja",
            "`clave_de_copia` da `<hoja>::<folio>`, así que las tres filas del "
            "mismo folio conviven sin colapsarse en el upsert.",
            len(set(claves)) == len(claves) and len(claves) >= 3,
            {"dedupe_keys": claves},
        ),
        (
            "El 100 % de una fase no cierra la cotización",
            "La maestra conserva su AVANCE y su ESTATUS pese a que las dos "
            "microtareas de CD están al 100 %.",
            float(maestra.get("avance") or 0) == 0.0
            and str(maestra.get("estatus")) == "EN PROCESO",
            {"avance_maestra": maestra.get("avance"),
             "estatus_maestra": maestra.get("estatus")},
        ),
        (
            "La maestra no hereda el concepto marcado",
            "El trabajador ve `[Calculo y Diseño]`; la maestra conserva su "
            "concepto limpio.",
            "[" not in str(maestra.get("concepto") or "")
            and all("[" in str(c) for c in conceptos),
            {"concepto_maestra": maestra.get("concepto"), "conceptos_micro": conceptos},
        ),
        (
            "Las microtareas no se sincronizan entre sí",
            "`campos_sincronizables` devuelve None para una fila con marca de "
            "fase: el 100 % de Miguel no se copia sobre la fila de Rolando.",
            asignacion.campos_sincronizables({
                "FOLIO": FOLIO, "AVANCE": "100", "ESTATUS": "HECHO",
                "CONCEPTO": f"COTIZAR NAVE [{rules.phase_label('CD')}]",
            }) is None,
            {},
        ),
        (
            "La papa caliente no pasa por el espejo de asignaciones",
            "`destinos_espejo` devuelve [] para una microtarea: su reparto es "
            "el de `apply_hot_potato`, no el de la asignación normal.",
            asignacion.destinos_espejo(MAESTRA, {
                "FOLIO": FOLIO, "RESPONSABLE": MIGUEL,
                "CONCEPTO": f"COTIZAR NAVE [{rules.phase_label('CD')}]",
            }, TONITA) == [],
            {},
        ),
    ]

    return [{"nombre": n, "explicacion": e, "cumple": bool(ok), "evidencia": ev}
            for n, e, ok, ev in comprobaciones]


# ----------------------------------------------------------------------
# Salida
# ----------------------------------------------------------------------

def _imprimir(traza: Dict[str, Any]) -> None:
    for paso in traza["pasos"]:
        print("=" * 72)
        print(paso["titulo"])
        print("-" * 72)
        respuesta = paso.get("respuesta")
        if respuesta is not None:
            print(f"  respuesta   : success={respuesta.get('success')} "
                  f"· {respuesta.get('message')}")
        maestra = paso["maestra"]
        print(f"  maestra     : AVANCE={maestra['avance']} "
              f"ESTATUS={maestra['estatus']} CONCEPTO={maestra['concepto']!r}")
        print(f"  MAP COT     : {maestra['map_cot'] or '(vacío)'}")
        resumen_log = [
            {k: v for k, v in e.items() if k in ("step", "assignee", "status")}
            for e in paso["proceso_log"]
        ]
        print(f"  PROCESO_LOG : {json.dumps(resumen_log, ensure_ascii=False)}")
        if paso["microtareas"]:
            for m in paso["microtareas"]:
                print(f"  microtarea  : [{m['hoja']}] {m['concepto']!r} "
                      f"ESTATUS={m['estatus']} AVANCE={m['avance']} "
                      f"clave={m['dedupe_key']}")
        else:
            print("  microtarea  : (ninguna)")
        print()

    print("=" * 72)
    print("INVARIANTES")
    print("-" * 72)
    for inv in traza["invariantes"]:
        print(f"  [{'OK ' if inv['cumple'] else 'NO '}] {inv['nombre']}")
        if inv["evidencia"]:
            print(f"        {json.dumps(inv['evidencia'], ensure_ascii=False)}")
    fallidas = [i for i in traza["invariantes"] if not i["cumple"]]
    print()
    print("TODAS LAS INVARIANTES SE CUMPLEN" if not fallidas
          else f"HAY {len(fallidas)} INVARIANTE(S) SIN CUMPLIR")


def main() -> int:
    traza = recorrer()
    if "--json" in sys.argv:
        print(json.dumps(traza, ensure_ascii=False, indent=2, default=str))
    else:
        _imprimir(traza)
    return 0 if all(i["cumple"] for i in traza["invariantes"]) else 1


if __name__ == "__main__":
    raise SystemExit(main())
