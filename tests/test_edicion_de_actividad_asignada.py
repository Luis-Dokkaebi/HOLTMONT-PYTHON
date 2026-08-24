"""
Editar desde el tracker propio una actividad que me asignaron.

El reporte (BUG-0015, ALFONSO CORREA, 2026-08-22): «de la celda 3 al 7 se le
agregó los porcentajes y comentarios y no se actualiza». Los renglones 3 al 7 de
su Tracker son actividades con folio `PPC-`, que lleva prefijo de secuencia
**global**: `compute_dedupe_key` devuelve el folio a secas, sin la hoja.

Qué pasaba. Cuando alguien le asigna una actividad, el espejo le deja fila
propia con clave de copia (`"ALFONSO CORREA::PPC-5442804"`) y la original se
queda con la clave global en la hoja de quien asignó. Al editar su fila —un
guardado normal, no una copia nueva—, `resolver_clave` resolvía a la clave
global y el upsert aterrizaba en la fila de la otra persona: el frontend recibía
«Guardado exitoso», la fila de Alfonso seguía igual, y al recargar volvían el
avance y las restricciones viejos.

La regla que fija este archivo: **si en alguna de mis hojas ya existe una fila
de ese folio, se escribe en esa**. La clave global solo manda cuando la fila
original es mía o cuando no tengo ninguna.
"""

from __future__ import annotations

import os
import sys
from typing import Any, Dict, List

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from backend.core.config import Settings  # noqa: E402
from backend.core.engines.memoria import MemoryEngine  # noqa: E402
from backend.repositories.tasks import TaskRepository  # noqa: E402
from backend.schemas.task import TaskWrite  # noqa: E402

FOLIO = "PPC-5442804"
CONCEPTO = "REUNION CON EL ING GERARDO BENITO PARA JUNTA CON EL DEP DE PRESUPUESTOS"
MIA = "ALFONSO CORREA"
DE_QUIEN_ASIGNA = "GERALDINE MORALES"


def _settings() -> Settings:
    return Settings(
        database_url=None,
        supabase_url=None,
        supabase_key=None,
        motor_forzado="memoria",
        escritura_habilitada=True,
    )


def _fila(dedupe_key: str, hoja: str, avance: float = 0.0,
          restricciones: str = "") -> Dict[str, Any]:
    return {
        "id": f"{abs(hash(dedupe_key)) % 10**12:012d}",
        "dedupe_key": dedupe_key,
        "folio": FOLIO,
        "folio_sintetico": False,
        "source_sheet": hoja,
        "assignee_raw": MIA,
        "concepto": CONCEPTO,
        "avance": avance,
        "status": "ASIGNADO",
        "fecha_alta": "2026-08-05",
        "restricciones": restricciones,
    }


def _motor(filas) -> MemoryEngine:
    return MemoryEngine({
        "tasks": [dict(f) for f in filas],
        "people": [{"id": "p-ac", "nombre": MIA},
                   {"id": "p-gm", "nombre": DE_QUIEN_ASIGNA}],
        "quotes": [],
        "profiles": [],
        "task_involucrados": [],
        "plan_semanal": [],
        "system_log": [],
    })


def _repo(filas) -> TaskRepository:
    return TaskRepository(_motor(filas), _settings())


# La situación del reporte: la original vive en la hoja de quien asignó y la
# copia —la fila que Alfonso ve y edita— en la suya.
ASIGNADA = [
    _fila(FOLIO, DE_QUIEN_ASIGNA),
    _fila(f"{MIA}::{FOLIO}", MIA),
]


# ======================================================================
# 1. La clave con la que se escribe
# ======================================================================

def test_mi_fila_manda_sobre_la_original_al_editarla_desde_mi_hoja() -> None:
    """Sin `como_copia`: un guardado normal desde mi tracker es MI fila."""
    repo = _repo(ASIGNADA)

    assert repo.resolver_clave(FOLIO, MIA, como_copia=False) == f"{MIA}::{FOLIO}"


def test_la_fila_original_conserva_su_clave_si_es_mia() -> None:
    """Si la global es de mi hoja, se sigue escribiendo con ella."""
    repo = _repo([_fila(FOLIO, MIA)])

    assert repo.resolver_clave(FOLIO, MIA, como_copia=False) == FOLIO


def test_editar_desde_una_hoja_ajena_no_estrena_fila() -> None:
    """
    El PPC maestro edita la fila del responsable, no una propia: sin fila mía,
    manda la clave global. Es la regla que ya fijaba
    `test_una_tarea_existente_no_cambia_de_dueno_al_editarla_desde_el_ppc`.
    """
    repo = _repo(ASIGNADA)

    assert repo.resolver_clave(FOLIO, "ADMINISTRADOR", como_copia=False) == FOLIO


# ======================================================================
# 2. El síntoma: el avance y las restricciones que se capturan
# ======================================================================

def test_el_avance_y_las_restricciones_se_guardan_en_mi_fila() -> None:
    repo = _repo(ASIGNADA)

    repo.guardar_lote(MIA, [TaskWrite.desde_hoja({
        "FOLIO": FOLIO,
        "CONCEPTO": CONCEPTO,
        "AVANCE %": 10,
        "RESTRICCIONES": "EN ESPERA DE LLAMADA",
    })])

    filas = repo.engine.select("tasks", donde={"folio": FOLIO})
    assert len(filas) == 2, "no se estrena una tercera fila"
    mia = next(f for f in filas if f["source_sheet"] == MIA)
    assert mia["avance"] == 10.0
    assert mia["restricciones"] == "EN ESPERA DE LLAMADA"


def test_lo_que_capturo_sigue_ahi_al_recargar_el_tracker() -> None:
    """El síntoma tal como se ve: recargar devolvía los valores viejos."""
    repo = _repo(ASIGNADA)

    repo.guardar_lote(MIA, [TaskWrite.desde_hoja({
        "FOLIO": FOLIO, "CONCEPTO": CONCEPTO,
        "AVANCE %": 50, "RESTRICCIONES": "EN ESPERA DE COTIZACION DE PROVEEDORES",
    })])
    repo.invalidar_caches()

    fila = next(t for t in repo.listar(MIA) if t.folio == FOLIO)
    assert fila.avance == 50.0
    assert fila.restricciones == "EN ESPERA DE COTIZACION DE PROVEEDORES"


def test_no_le_escribo_las_restricciones_a_quien_me_la_asigno() -> None:
    """
    La otra mitad del defecto: mi captura caía en la fila de la otra persona.

    Lo que sí viaja a las demás copias es el estado (AVANCE, ESTATUS), y lo
    hace por `_sincronizar_copias`, no por el upsert.
    """
    repo = _repo(ASIGNADA)

    repo.guardar_lote(MIA, [TaskWrite.desde_hoja({
        "FOLIO": FOLIO, "CONCEPTO": CONCEPTO,
        "AVANCE %": 10, "RESTRICCIONES": "EN ESPERA DE LLAMADA",
    })])

    original = next(f for f in repo.engine.select("tasks", donde={"folio": FOLIO})
                    if f["source_sheet"] == DE_QUIEN_ASIGNA)
    assert original["restricciones"] == ""
    assert original["avance"] == 0.0


def test_la_copia_a_la_hoja_de_otra_persona_sigue_teniendo_clave_propia() -> None:
    """El arreglo no puede colapsar la asignación: cada quien, su fila."""
    repo = _repo([_fila(FOLIO, MIA)])

    assert repo.resolver_clave(FOLIO, DE_QUIEN_ASIGNA, como_copia=True) == \
        f"{DE_QUIEN_ASIGNA}::{FOLIO}"


def test_sin_folio_no_hay_clave_que_resolver() -> None:
    repo = _repo(ASIGNADA)

    assert repo.resolver_clave("", MIA) is None
    assert repo.resolver_clave(None, MIA) is None


def test_sin_base_manda_la_clave_historica() -> None:
    """
    Si no se puede preguntar quién es el dueño, se escribe con la clave de
    siempre: inventar identidad sin evidencia duplicaría filas.
    """
    motor = _motor(ASIGNADA)

    def revienta(*_args, **_kwargs):
        raise RuntimeError("la base no responde")

    motor.select = revienta  # type: ignore[method-assign]
    repo = TaskRepository(motor, _settings())

    assert repo.resolver_clave(FOLIO, MIA, como_copia=False) == FOLIO
    assert repo.resolver_clave(FOLIO, MIA, como_copia=True) == FOLIO


# ======================================================================
# 3. Guardar Todo no multiplica los viajes a la base
# ======================================================================

def test_guardar_todo_resuelve_los_folios_en_una_sola_consulta() -> None:
    """
    Saber de quién es cada fila cuesta una consulta; hacerla por renglón
    convertiría «Guardar Todo» de 50 filas en 50 viajes a la base.
    """
    folios = [f"PPC-100{i}" for i in range(10)]
    filas = [_fila(f"{MIA}::{f}", MIA) | {"folio": f, "dedupe_key": f"{MIA}::{f}"}
             for f in folios]
    motor = _motor(filas)

    consultas: List[Dict[str, Any]] = []
    select_original = motor.select

    def espiar(tabla: str, **kwargs):
        consultas.append({"tabla": tabla, **kwargs})
        return select_original(tabla, **kwargs)

    motor.select = espiar  # type: ignore[method-assign]
    repo = TaskRepository(motor, _settings())

    repo.guardar_lote(MIA, [TaskWrite.desde_hoja(
        {"FOLIO": f, "CONCEPTO": CONCEPTO, "AVANCE %": 25}) for f in folios])

    por_folio = [c for c in consultas
                 if c["tabla"] == "tasks" and "folio" in (c.get("donde_en") or c.get("donde") or {})]
    assert len(por_folio) == 1, f"una sola consulta por lote, no {len(por_folio)}"
    guardadas = {f["dedupe_key"]: f["avance"]
                 for f in select_original("tasks", donde={"source_sheet": MIA})}
    assert set(guardadas) == {f"{MIA}::{f}" for f in folios}
    assert set(guardadas.values()) == {25.0}


# ======================================================================
# 4. El camino vivo, de punta a punta
# ======================================================================

@pytest.fixture
def puente(monkeypatch):
    """`save_tracker_batch` sobre `MemoryEngine`, como lo llama `index.html`."""
    import backend.core.engine as core_engine
    import backend.services.persistencia as persistencia

    motor = _motor(ASIGNADA)
    monkeypatch.setenv("BACKEND_ENGINE", "memoria")
    monkeypatch.setattr(core_engine, "construir_engine", lambda *a, **k: motor)
    original = persistencia.PersistenciaTracker.__init__
    monkeypatch.setattr(persistencia.PersistenciaTracker, "__init__",
                        lambda self, engine=None: original(self, motor))
    return motor


def test_el_guardado_del_tracker_actualiza_la_fila_de_quien_captura(puente) -> None:
    """
    El reporte completo: Alfonso pone el porcentaje y el comentario en su
    Tracker, guarda, y al recargar siguen ahí.
    """
    from api.services import tracker_store

    respuesta = tracker_store.save_tracker_batch(MIA, [{
        "FOLIO": FOLIO,
        "ALTA": "C",
        "FECHA": "2026-08-05",
        "HORA": "08:28",
        "CLASIFICACION": "A",
        "CONCEPTO": CONCEPTO,
        "INVOLUCRADOS": MIA,
        "AVANCE %": 10,
        "RELOJ": "17",
        "RESTRICCIONES": "EN ESPERA DE LLAMADA",
        "PRIORIDADES": "BAJA",
        "RIESGOS": "BAJO",
        "STATUS": "ASIGNADO",
    }], "ALFONSO_CORREA")

    assert respuesta["success"] is True, respuesta.get("message")

    repo = TaskRepository(puente, _settings())
    fila = next(t for t in repo.listar(MIA) if t.folio == FOLIO)
    assert fila.avance == 10.0, "el porcentaje capturado se perdía"
    assert fila.restricciones == "EN ESPERA DE LLAMADA", "el comentario se perdía"
