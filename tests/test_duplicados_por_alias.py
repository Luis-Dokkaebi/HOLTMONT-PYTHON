"""
Una persona, una partición: sus dos nombres no pueden duplicarle las tareas.

Reporte del dueño (2026-08-14), con captura de la tabla de Carlos Méndez: cada
actividad aparecía **dos veces** (REVISION DE CORREOS ELECTRONICOS, REALIZAR
REPORTE FOTOGRAFICO…, CERRAR GRUPOS DE PROYECTOS FACTURADOS, en renglones
consecutivos).

Medido contra la base real antes de escribir una línea: 61 filas duplicadas en
`tasks`, todas del mismo patrón —el mismo folio, la misma persona, en dos
particiones— y ninguna con `dedupe_key` repetida, así que la restricción única
de la base no las veía:

    CARLOS MENDEZ / CARLOS MENDEZ URBINA .................. 10 folios PPC-
    CESAR EDUARDO GARCIA AVALOS / …AVALOS2 ................ 36 folios
    ROCIO ABIGAIL CASTRO COVARRUBIA / …COVARRUBIAS ........ 15 folios

El mecanismo, para los tres:

  1. Una persona tiene **dos** nombres que no son iguales: el de su hoja
     (`staff_name`, "CARLOS MENDEZ") y el del directorio (`label`, "CARLOS
     MENDEZ URBINA"), que es el que ofrece el selector de involucrados.
  2. Al guardar con el responsable escrito con el segundo nombre,
     `asignacion.hoja_de_persona` devolvía ese texto tal cual, así que
     `destinos_espejo` lo tomaba por **otra** persona y escribía una copia.
  3. La copia no colisiona: `resolver_clave` le da identidad propia
     (`"CARLOS MENDEZ URBINA::PPC-544684601"`) porque comparaba el nombre de
     hoja literalmente y no encontraba la fila global de esa misma persona.
  4. La lectura sí une las dos particiones (`hojas_del_tracker`), y por eso la
     tarea sale duplicada en la tabla de su dueño.

Lo que se fija aquí: la escritura resuelve el nombre a la hoja canónica del
organigrama (1 y 2), y la identidad de fila reconoce como "mía" cualquier
partición de la misma persona (3). Lo que **no** se toca: la copia legítima a
otra persona, que es la difusión lateral ("papa caliente") y sigue necesitando
fila propia.
"""

from __future__ import annotations

import os
import sys

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from api.services import asignacion, organigrama  # noqa: E402
from api.services import tracker_rules as rules  # noqa: E402
from backend.core.config import Settings  # noqa: E402
from backend.core.engines.memoria import MemoryEngine  # noqa: E402
from backend.repositories.tasks import TaskRepository  # noqa: E402
from backend.schemas.task import TaskWrite  # noqa: E402

# Los dos nombres de Carlos, tal como los guarda `PERFILES`/`profiles`.
HOJA = "CARLOS MENDEZ"                    # staff_name: la que abre su Tracker
NOMBRE_DEL_DIRECTORIO = "CARLOS MENDEZ URBINA"   # label: lo que ofrece el selector

# Un folio de secuencia global: su `dedupe_key` es el folio a secas, y de ahí
# viene la copia con clave propia.
FOLIO = "PPC-544684601"
CONCEPTO = "REALIZAR REPORTE FOTOGRAFICO 2023 Y 2024 DE DANHIL"


@pytest.fixture(autouse=True)
def _sin_cache_de_perfiles():
    """`hoja_canonica` resuelve por perfil: la caché no puede cruzar pruebas."""
    organigrama.reset_cache_perfiles()
    yield
    organigrama.reset_cache_perfiles()


# ---------------------------------------------------------------------------
# 1. El traductor: cualquiera de sus nombres lleva a una sola hoja
# ---------------------------------------------------------------------------

def test_el_nombre_del_directorio_resuelve_a_la_hoja_del_tracker() -> None:
    assert organigrama.hoja_canonica(NOMBRE_DEL_DIRECTORIO) == HOJA


def test_la_hoja_canonica_se_resuelve_a_si_misma() -> None:
    assert organigrama.hoja_canonica(HOJA) == HOJA


def test_una_persona_desconocida_no_estrena_hoja_canonica() -> None:
    """Vacío y no el nombre recibido: quien llama tiene que poder distinguirlo."""
    assert organigrama.hoja_canonica("PERSONA QUE NO EXISTE") == ""


def test_la_tabla_de_ventas_no_es_la_hoja_de_una_persona() -> None:
    assert organigrama.hoja_canonica(rules.SALES_MASTER_SHEET) == ""


# ---------------------------------------------------------------------------
# 2. El destino de una asignación: el nombre largo no estrena partición
# ---------------------------------------------------------------------------

def test_el_destino_del_nombre_del_directorio_es_la_hoja_canonica() -> None:
    """La prueba que fallaba antes del arreglo: devolvía "CARLOS MENDEZ URBINA"."""
    assert asignacion.hoja_de_persona(NOMBRE_DEL_DIRECTORIO) == HOJA


def test_asignarse_algo_con_el_otro_nombre_no_produce_espejo() -> None:
    """
    Carlos guarda en su tabla una actividad cuyo RESPONSABLE es su nombre largo.

    Es exactamente lo que pasó el 2026-08-13: diez actividades suyas se
    copiaron a una segunda partición y su tabla las mostró por duplicado.
    """
    destinos = asignacion.destinos_espejo(
        HOJA, {"FOLIO": FOLIO, "CONCEPTO": CONCEPTO, "RESPONSABLE": NOMBRE_DEL_DIRECTORIO})

    assert destinos == [], f"no hay a quién copiar: {NOMBRE_DEL_DIRECTORIO} es {HOJA}"


def test_la_asignacion_a_otra_persona_si_produce_espejo() -> None:
    """El arreglo no puede apagar la difusión lateral."""
    destinos = asignacion.destinos_espejo(
        HOJA, {"FOLIO": FOLIO, "CONCEPTO": CONCEPTO,
               "RESPONSABLE": f"{NOMBRE_DEL_DIRECTORIO}, RICARDO MENDO"})

    assert destinos == ["RICARDO MENDO"]


def test_el_nombre_del_directorio_de_otra_persona_tambien_se_canoniza() -> None:
    """
    Asignar a "Ricardo Alonso Mendo Morales" (el `label`) tiene que caer en
    "RICARDO MENDO" (su `staff_name`), no estrenar una tercera partición.
    """
    destinos = asignacion.destinos_espejo(
        HOJA, {"FOLIO": FOLIO, "CONCEPTO": CONCEPTO,
               "RESPONSABLE": "RICARDO ALONSO MENDO MORALES"})

    assert destinos == ["RICARDO MENDO"]


# ---------------------------------------------------------------------------
# 3. La identidad de fila: una partición alias no es "otra hoja"
# ---------------------------------------------------------------------------

def _settings() -> Settings:
    return Settings(
        database_url=None,
        supabase_url=None,
        supabase_key=None,
        motor_forzado="memoria",
        escritura_habilitada=True,
    )


def _repo(filas) -> TaskRepository:
    engine = MemoryEngine({
        "tasks": list(filas),
        "people": [{"id": "p-cm", "nombre": HOJA}],
        "profiles": [],
        "task_involucrados": [],
        "system_log": [],
    })
    return TaskRepository(engine, _settings())


def _fila_de_carlos(hoja: str = HOJA) -> dict:
    return {
        "id": "aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa",
        "dedupe_key": FOLIO,
        "folio": FOLIO,
        "folio_sintetico": False,
        "source_sheet": hoja,
        "assignee_raw": NOMBRE_DEL_DIRECTORIO,
        "concepto": CONCEPTO,
        "avance": 0.0,
        "status": "ASIGNADO",
        "fecha_alta": "2026-08-12",
    }


def test_la_clave_de_una_copia_a_mi_propia_hoja_alias_es_la_global() -> None:
    """
    Pedida como copia hacia el nombre largo, la fila que ya existe en la hoja
    canónica sigue siendo la misma fila.
    """
    repo = _repo([_fila_de_carlos()])

    assert repo.resolver_clave(FOLIO, NOMBRE_DEL_DIRECTORIO, como_copia=True) == FOLIO


def test_guardar_como_copia_en_la_hoja_alias_no_duplica_la_tarea() -> None:
    """La prueba de regresión del reporte: una tarea, una fila."""
    repo = _repo([_fila_de_carlos()])

    repo.guardar_lote(
        NOMBRE_DEL_DIRECTORIO,
        [TaskWrite(folio=FOLIO, concepto=CONCEPTO, avance=50.0)],
        como_copia=True,
    )

    filas = repo.engine.select("tasks", donde={"folio": FOLIO})
    assert len(filas) == 1, f"se duplicó la tarea en {[f['source_sheet'] for f in filas]}"
    assert filas[0]["source_sheet"] == HOJA, "la fila se queda en la hoja que él abre"
    assert filas[0]["avance"] == 50.0, "el avance capturado sí se guarda"


def test_la_tabla_de_carlos_no_muestra_la_tarea_dos_veces() -> None:
    """
    El síntoma tal como se ve: su Tracker une sus dos particiones, así que la
    única defensa es que no haya dos filas.
    """
    repo = _repo([_fila_de_carlos()])
    repo.guardar_lote(NOMBRE_DEL_DIRECTORIO,
                      [TaskWrite(folio=FOLIO, concepto=CONCEPTO)], como_copia=True)
    repo.invalidar_caches()

    conceptos = [t.concepto for t in repo.listar(HOJA)]
    assert conceptos.count(CONCEPTO) == 1, conceptos


def test_la_copia_a_la_hoja_de_otra_persona_sigue_teniendo_clave_propia() -> None:
    """
    Difusión lateral: `RM-8909` asignada a Carlos por Ricardo necesita fila
    propia en cada tabla. El arreglo no puede colapsarlas.
    """
    repo = _repo([_fila_de_carlos()])

    clave = repo.resolver_clave(FOLIO, "RICARDO MENDO", como_copia=True)

    assert clave == f"RICARDO MENDO::{FOLIO}"


def test_una_tarea_existente_no_cambia_de_dueno_al_editarla_desde_el_ppc() -> None:
    """
    Sin `como_copia` nada cambia: editar desde el PPC maestro actualiza la fila
    del responsable, no estrena otra.
    """
    repo = _repo([_fila_de_carlos()])

    assert repo.resolver_clave(FOLIO, "ADMINISTRADOR", como_copia=False) == FOLIO
