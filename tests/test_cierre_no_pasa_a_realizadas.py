"""
Poner una actividad al 100 % y que no baje a TAREAS REALIZADAS.

Reporte (BUG-0023, ALFONSO_CORREA, 2026-08-31): «las celdas del 1,3,4,5,6,7 son
actividades ya realizadas y las puse al cien % y siguen igual».

Es el mismo mecanismo del duplicado por alias (`test_duplicados_por_alias.py`),
por el hueco que aquel arreglo dejó abierto. Una persona tiene **dos** nombres
—el de su hoja (`staff_name`, "ALFONSO CORREA") y el del directorio (`label`,
"Alfonso Correa De Leon"), que es el que ofrecía el selector de involucrados— y
la lectura une las dos particiones (`hojas_del_tracker`). La escritura no:

* Para un folio de secuencia global (`PPC-`, `AV-`) `resolver_clave` sí
  pregunta a la base y escribe en MI fila viva en cualquiera de mis
  particiones. Es la regla que fijó BUG-0015.
* Para un folio con **iniciales de persona** (`GM-0123`, `JO-0009`) la clave es
  `"<hoja>::<folio>"` y la función devolvía esa clave **sin preguntar nada**.
  Si mi fila vive en la partición alias, la clave calculada no es la suya: el
  upsert no encuentra nada que actualizar e **inserta una fila nueva** en la
  otra partición.

El resultado en pantalla es exactamente el reporte: la fila que Alfonso puso al
100 % sigue en la tabla con su avance viejo —porque la suya nunca se tocó— y
además aparece una copia al 100 % bajo TAREAS REALIZADAS. Cuantas veces la
vuelva a cerrar, sigue igual.

La regla que fija este archivo: **si en alguna de mis particiones ya existe una
fila de ese folio, se escribe en esa**, lleve el folio prefijo global o
iniciales. Lo que no cambia es la difusión lateral: el mismo folio con
iniciales en la tabla de OTRA persona es otra fila y se queda intacta.
"""

from __future__ import annotations

import os
import sys
from typing import Any, Dict, List

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from api.services import organigrama  # noqa: E402
from api.services import sheets  # noqa: E402
from backend.core.config import Settings  # noqa: E402
from backend.core.engines.memoria import MemoryEngine  # noqa: E402
from backend.repositories.tasks import TaskRepository, esta_archivada  # noqa: E402
from backend.schemas.task import TaskWrite  # noqa: E402
from backend.services.persistencia import PersistenciaTracker  # noqa: E402

# Los dos nombres de Alfonso, tal como los guarda `PERFILES`/`profiles`.
HOJA = "ALFONSO CORREA"                      # staff_name: la que abre su Tracker
HOJA_ALIAS = "Alfonso Correa De Leon"        # label: lo que ofrecía el selector

# Folio con iniciales de quien se la asignó. NO es de secuencia global, así que
# su `dedupe_key` es "<hoja>::<folio>" y ahí está el defecto.
FOLIO = "GM-0123"
CONCEPTO = "REVISION DE PLANOS ESTRUCTURALES"
OTRA_PERSONA = "RICARDO MENDO"


@pytest.fixture(autouse=True)
def _sin_cache_de_perfiles():
    """`hojas_de_persona` resuelve por perfil: la caché no puede cruzar pruebas."""
    organigrama.reset_cache_perfiles()
    yield
    organigrama.reset_cache_perfiles()


def _settings() -> Settings:
    return Settings(
        database_url=None,
        supabase_url=None,
        supabase_key=None,
        motor_forzado="memoria",
        escritura_habilitada=True,
    )


def _fila(hoja: str, clave: str, avance: float = 30.0) -> Dict[str, Any]:
    return {
        "id": f"{abs(hash(clave)) % 10**12:012d}",
        "dedupe_key": clave,
        "folio": FOLIO,
        "folio_sintetico": False,
        "source_sheet": hoja,
        "assignee_raw": HOJA,
        "concepto": CONCEPTO,
        "avance": avance,
        "status": "ASIGNADO",
        "cumplimiento": "",
        "fecha_alta": "2026-08-20",
    }


def _motor(filas: List[Dict[str, Any]]) -> MemoryEngine:
    return MemoryEngine({
        "tasks": [dict(f) for f in filas],
        "people": [{"id": "p-ac", "nombre": HOJA}],
        "quotes": [],
        "profiles": [],
        "task_involucrados": [],
        "plan_semanal": [],
        "system_log": [],
    })


def _repo(filas: List[Dict[str, Any]]) -> TaskRepository:
    return TaskRepository(_motor(filas), _settings())


# La situación del reporte: la fila de Alfonso quedó en su partición alias, que
# es la que ve pero no la que su nombre de hoja calcula.
EN_LA_ALIAS = [_fila(HOJA_ALIAS, f"{HOJA_ALIAS}::{FOLIO}")]


# ======================================================================
# 1. La clave con la que se escribe
# ======================================================================

def test_su_tracker_lee_las_dos_particiones() -> None:
    """La premisa del defecto: por eso ve la fila que no puede actualizar."""
    assert _repo(EN_LA_ALIAS).hojas_del_tracker(HOJA) == [HOJA, HOJA_ALIAS]


def test_mi_fila_en_la_particion_alias_manda_sobre_la_clave_calculada() -> None:
    """
    La prueba que falla antes del arreglo: devolvía "ALFONSO CORREA::GM-0123",
    una clave que no existe en la base.
    """
    assert _repo(EN_LA_ALIAS).resolver_clave(FOLIO, HOJA) == f"{HOJA_ALIAS}::{FOLIO}"


def test_si_mi_fila_ya_esta_en_mi_hoja_conserva_su_clave() -> None:
    filas = [_fila(HOJA, f"{HOJA}::{FOLIO}")]

    assert _repo(filas).resolver_clave(FOLIO, HOJA) == f"{HOJA}::{FOLIO}"


def test_sin_ninguna_fila_mia_la_clave_es_la_de_siempre() -> None:
    """Un folio que no está en la base se estrena con la clave calculada."""
    assert _repo([]).resolver_clave(FOLIO, HOJA) == f"{HOJA}::{FOLIO}"


def test_sin_base_manda_la_clave_historica() -> None:
    """Preguntar no se puede: inventar identidad sin evidencia duplicaría filas."""
    motor = _motor(EN_LA_ALIAS)

    def revienta(*_args, **_kwargs):
        raise RuntimeError("la base no responde")

    motor.select = revienta  # type: ignore[method-assign]

    assert TaskRepository(motor, _settings()).resolver_clave(FOLIO, HOJA) == \
        f"{HOJA}::{FOLIO}"


# ======================================================================
# 2. El síntoma: cerrar al 100 % y que la tabla siga igual
# ======================================================================

def test_cerrar_al_100_baja_la_fila_a_tareas_realizadas() -> None:
    """El reporte, tal como se ve: la actividad tiene que salir de las activas."""
    repo = _repo(EN_LA_ALIAS)

    repo.guardar_lote(HOJA, [TaskWrite.desde_hoja(
        {"FOLIO": FOLIO, "CONCEPTO": CONCEPTO, "AVANCE %": "100"})])
    repo.invalidar_caches()

    activas, archivadas = repo.particionar(HOJA)
    assert [t.folio for t in activas] == []
    assert [(t.folio, t.avance) for t in archivadas] == [(FOLIO, 100.0)]


def test_cerrar_al_100_no_estrena_una_segunda_fila() -> None:
    """La otra mitad del defecto: la copia al 100 % en la partición equivocada."""
    repo = _repo(EN_LA_ALIAS)

    repo.guardar_lote(HOJA, [TaskWrite.desde_hoja(
        {"FOLIO": FOLIO, "CONCEPTO": CONCEPTO, "AVANCE %": "100"})])

    filas = repo.engine.select("tasks", donde={"folio": FOLIO})
    assert len(filas) == 1, f"se duplicó en {[f['source_sheet'] for f in filas]}"
    assert filas[0]["source_sheet"] == HOJA_ALIAS, "la fila no cambia de partición"
    assert filas[0]["avance"] == 100.0


def test_el_camino_legacy_del_tracker_tambien_cierra_la_fila() -> None:
    """
    Lo que manda `index.html`: encabezados de hoja por `PersistenciaTracker`.

    `AVANCE %` es el nombre con el que la lectura rinde la columna
    (`sheets.TASK_HEADER_MAP`), así que es literalmente lo que vuelve al
    guardar.
    """
    motor = _motor(EN_LA_ALIAS)
    guardado = PersistenciaTracker(motor).guardar(HOJA, [{
        "FOLIO": FOLIO, "CONCEPTO": CONCEPTO, "AVANCE %": "100",
        "INVOLUCRADOS": HOJA, "STATUS": "ASIGNADO",
    }])

    assert guardado.exito, guardado.mensaje
    filas = motor.select("tasks", donde={"folio": FOLIO})
    assert len(filas) == 1, f"se duplicó en {[f['source_sheet'] for f in filas]}"
    assert esta_archivada(filas[0]), "al 100 % la fila va a TAREAS REALIZADAS"


def test_la_vista_la_pinta_bajo_el_separador() -> None:
    """
    La forma que recibe el frontend: `{data, history}` se reconstruye colocando
    las archivadas debajo del rótulo. Sin el arreglo, la fila vieja quedaba
    arriba y la nueva abajo: la actividad salía dos veces y «seguía igual».
    """
    motor = _motor(EN_LA_ALIAS)
    PersistenciaTracker(motor).guardar(HOJA, [{
        "FOLIO": FOLIO, "CONCEPTO": CONCEPTO, "AVANCE %": "100",
    }])

    valores = sheets._valores_de_tareas(motor.select("tasks"))
    rotulo = [i for i, fila in enumerate(valores)
              if sheets.SEPARADOR_ARCHIVO in "|".join(str(c) for c in fila)]
    assert rotulo, "la matriz tiene que traer el separador"
    # Encabezados, separador y una sola fila, debajo.
    assert len(valores) == 3 and rotulo == [1]


# ======================================================================
# 3. Lo que el arreglo no puede romper: la difusión lateral
# ======================================================================

def test_la_fila_de_otra_persona_con_el_mismo_folio_no_es_mia() -> None:
    """
    `GM-0123` puede vivir en varios trackers por papa caliente. Cada copia es
    una fila legítima y escribir en la ajena sería el defecto de BUG-0015 al
    revés.
    """
    filas = [_fila(OTRA_PERSONA, f"{OTRA_PERSONA}::{FOLIO}")]

    assert _repo(filas).resolver_clave(FOLIO, HOJA) == f"{HOJA}::{FOLIO}"


def test_cerrar_la_mia_no_toca_la_de_la_otra_persona() -> None:
    repo = _repo([_fila(HOJA_ALIAS, f"{HOJA_ALIAS}::{FOLIO}"),
                  _fila(OTRA_PERSONA, f"{OTRA_PERSONA}::{FOLIO}")])

    repo.guardar_lote(HOJA, [TaskWrite.desde_hoja(
        {"FOLIO": FOLIO, "CONCEPTO": CONCEPTO, "AVANCE %": "100"})])

    ajena = next(f for f in repo.engine.select("tasks", donde={"folio": FOLIO})
                 if f["source_sheet"] == OTRA_PERSONA)
    assert ajena["avance"] == 30.0


def test_la_copia_a_otra_persona_sigue_teniendo_clave_propia() -> None:
    """Asignar `GM-0123` a alguien más le estrena su fila, no colapsa la mía."""
    repo = _repo([_fila(HOJA, f"{HOJA}::{FOLIO}")])

    assert repo.resolver_clave(FOLIO, OTRA_PERSONA, como_copia=True) == \
        f"{OTRA_PERSONA}::{FOLIO}"


def test_asignarme_algo_que_ya_tengo_no_estrena_una_copia() -> None:
    """
    Pedida como copia hacia mi nombre del directorio, la fila que ya existe en
    la partición que abro sigue siendo la misma fila.
    """
    repo = _repo([_fila(HOJA, f"{HOJA}::{FOLIO}")])

    assert repo.resolver_clave(FOLIO, HOJA_ALIAS, como_copia=True) == \
        f"{HOJA}::{FOLIO}"


# ======================================================================
# 4. La otra grafía de la misma hoja
# ======================================================================

def test_una_particion_con_espacio_inicial_es_la_misma_hoja() -> None:
    """
    `source_sheet` no está normalizado: hay hojas reales con espacio inicial
    (" LILIANA AYLIN MARTINEZ IBARRA") y la clave almacenada lo conserva.
    """
    filas = [_fila(f" {HOJA}", f" {HOJA}::{FOLIO}")]

    assert _repo(filas).resolver_clave(FOLIO, HOJA) == f" {HOJA}::{FOLIO}"


# ======================================================================
# 5. Saber a cuánta gente le pasa
# ======================================================================

def test_las_particiones_partidas_se_pueden_enumerar() -> None:
    """
    «Revisar que no esté pasando con otros usuarios» tiene respuesta medible:
    toda persona cuyo tracker se lee de dos particiones es candidata, porque
    hasta el arreglo la mitad de sus filas no se podía actualizar.
    """
    repo = _repo([_fila(HOJA_ALIAS, f"{HOJA_ALIAS}::{FOLIO}"),
                  _fila(HOJA, f"{HOJA}::AC-0001"),
                  _fila(OTRA_PERSONA, f"{OTRA_PERSONA}::{FOLIO}")])

    assert len(repo.hojas_del_tracker(HOJA)) == 2
    assert len(repo.hojas_del_tracker(OTRA_PERSONA)) == 1
