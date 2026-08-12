"""
Una persona, un tracker: los dos nombres de la misma persona apuntan a la misma hoja.

Reporte del dueño (2026-08-12): «VANESSA_DE_LARA dice que guardó varias
actividades y no se guardan».

Se reprodujo en el navegador. Se guardan: el `POST /api/savePPC` responde 200 y
la vista dice «Guardado». Lo que falla es **dónde** caen, y el motivo es que el
nombre de la hoja se decide en dos sitios distintos que pueden no coincidir:

  * su Tracker abre la hoja que dice el organigrama
    (`organigrama.nombre_de_hoja('VANESSA_DE_LARA')` -> `staff_name`, "VANESSA
     DE LARA");
  * el selector de involucrados ofrece los nombres de la tabla `people`
    (`allStaffList` en `index.html` sale de `config.directory`), y el guardado
    archivaba la actividad bajo **ese** nombre.

Cuando los dos textos difieren —y difieren: `PERFILES` guarda `staff_name` y
`label` por separado justo porque no son iguales— la actividad se guarda en una
partición que ella no abre por ningún lado. Nadie ve un error: el sistema
reporta éxito y la tarea existe, invisible.

Peor todavía era el último recurso: una persona que no estuviera en `people`
mandaba su actividad a `ADMINISTRADOR`, contradiciendo el propio comentario de
`HOJA_PPC_POR_DEFECTO` ("donde caen las tareas nuevas del PPC **que no traen
responsable**").

Lo que se fija aquí:

  1. `organigrama.hojas_de_persona` traduce cualquiera de los nombres conocidos
     de una persona a la hoja canónica de su tracker.
  2. Al guardar, el responsable se resuelve por ahí: la actividad cae en la
     hoja que abre su Tracker.
  3. Al leer, una hoja de persona incluye lo guardado bajo sus otros nombres,
     para que lo que ya se archivó mal reaparezca.
  4. `ADMINISTRADOR` queda **solo** para las filas sin responsable.
"""

from __future__ import annotations

import pytest

from api.services import organigrama, sheets
from api.services import work_order
from backend.core.engines.memoria import MemoryEngine
from backend.services.persistencia import HOJA_PPC_POR_DEFECTO, PersistenciaTracker

# Los dos nombres de la misma persona, tal como los guarda `PERFILES`.
HOJA_DEL_TRACKER = "VANESSA DE LARA"          # staff_name: lo que abre su vista
NOMBRE_DEL_DIRECTORIO = "ERIKA VANESSA RODRIGUEZ DE LARA"


def tarea_guardada(folio: str, hoja: str, concepto: str) -> dict:
    return {
        "id": f"id-{folio}",
        "dedupe_key": f"{hoja}::{folio}",
        "folio": folio,
        "folio_sintetico": False,
        "source_sheet": hoja,
        "assignee_raw": hoja,
        "concepto": concepto,
        "avance": 0.0,
        "status": "ASIGNADO",
    }


@pytest.fixture
def motor(monkeypatch):
    """Base en memoria con la persona registrada con su nombre largo."""
    engine = MemoryEngine({
        "tasks": [],
        "quotes": [],
        "people": [{"id": "p-van", "nombre": NOMBRE_DEL_DIRECTORIO,
                    "departamento": "COMPRAS", "tipo_hoja": "ESTANDAR"}],
        "profiles": [],
        "plan_semanal": [],
        "task_involucrados": [],
        "system_log": [],
        "work_orders": [],
    })
    monkeypatch.setattr(work_order, "_persistencia", lambda: PersistenciaTracker(engine))
    monkeypatch.setattr(work_order, "_engine", lambda: engine)
    organigrama.reset_cache_perfiles()
    yield engine
    organigrama.reset_cache_perfiles()


def actividad(concepto: str, responsable: str, folio: str) -> dict:
    """Una fila de la cola de "Agregar Actividad", como la manda `submitBatch`."""
    return {"id": folio, "concepto": concepto, "responsable": responsable,
            "especialidad": "COMPRAS", "clasificacion": "A", "prioridad": "MEDIA",
            "riesgos": "BAJO", "fechaRespuesta": "01/09/26", "cumplimiento": "NO"}


def hojas_con_tareas(engine: MemoryEngine) -> dict:
    salida: dict = {}
    for fila in engine.select("tasks"):
        salida.setdefault(fila["source_sheet"], []).append(fila["concepto"])
    return salida


# ---------------------------------------------------------------------------
# 1. El traductor de nombres
# ---------------------------------------------------------------------------

def test_el_nombre_del_directorio_lleva_a_la_hoja_del_tracker() -> None:
    hojas = organigrama.hojas_de_persona(NOMBRE_DEL_DIRECTORIO)
    assert hojas and hojas[0] == HOJA_DEL_TRACKER, (
        "el nombre largo tiene que resolver a la hoja que abre su Tracker"
    )


def test_la_hoja_del_tracker_se_resuelve_a_si_misma() -> None:
    assert organigrama.hojas_de_persona(HOJA_DEL_TRACKER)[0] == HOJA_DEL_TRACKER


def test_los_dos_nombres_aparecen_entre_las_equivalentes() -> None:
    """La lectura las necesita todas para no perder lo ya guardado."""
    hojas = {h.upper() for h in organigrama.hojas_de_persona(HOJA_DEL_TRACKER)}
    assert NOMBRE_DEL_DIRECTORIO.upper() in hojas


def test_una_persona_desconocida_no_inventa_hoja() -> None:
    assert organigrama.hojas_de_persona("PERSONA QUE NO EXISTE") == ()


def test_una_cuenta_de_control_no_secuestra_la_hoja_de_una_persona() -> None:
    """
    `JAIME_OLIVO` es una cuenta de control: su `staff_name` está vacío y su
    etiqueta es "Jaime Olivo". Quien tiene ese tracker es `INGE_OLIVO`, con
    `staff_name` "JAIME OLIVO".

    Resolver por etiqueta habría devuelto "Jaime Olivo" y estrenado una
    partición con esa capitalización, separada de la que ya tiene sus tareas.
    """
    assert organigrama.hojas_de_persona("JAIME OLIVO")[0] == "JAIME OLIVO"


def test_la_hoja_canonica_conserva_la_grafia_almacenada() -> None:
    """Nunca se devuelve la etiqueta como canónica: `source_sheet` va en mayúsculas."""
    for nombre in ("JAIME OLIVO", NOMBRE_DEL_DIRECTORIO, "LILIANA MARTINEZ IBARRA"):
        hojas = organigrama.hojas_de_persona(nombre)
        if hojas:
            assert hojas[0] == hojas[0].upper(), (
                f"{nombre!r} resolvió a {hojas[0]!r}, que no es la grafía de la hoja"
            )


def test_la_hoja_maestra_de_ventas_no_se_traduce() -> None:
    """
    `ANTONIA_VENTAS` es el core de ventas, no el tracker de nadie (AGENTS.md §3).

    Traducirlo a su tracker personal metería cotizaciones donde no van.
    """
    assert organigrama.hojas_de_persona("ANTONIA_VENTAS") == ()


# ---------------------------------------------------------------------------
# 2. Al guardar: la actividad cae donde ella la ve
# ---------------------------------------------------------------------------

def test_la_actividad_capturada_cae_en_la_hoja_de_su_tracker(motor) -> None:
    """El defecto reportado, por el camino de "Agregar Actividad"."""
    res = work_order.process_and_save_work_order(
        [actividad("PEDIR COTIZACION A PROVEEDOR", NOMBRE_DEL_DIRECTORIO, "PPC-900001")],
        "VANESSA_DE_LARA")

    assert res["success"] is True, res.get("message")
    assert list(hojas_con_tareas(motor)) == [HOJA_DEL_TRACKER], (
        f"la actividad quedó en {list(hojas_con_tareas(motor))} y su Tracker abre "
        f"{HOJA_DEL_TRACKER!r}"
    )


def test_varias_actividades_seguidas_caen_todas_en_su_hoja(motor) -> None:
    """«Guardó varias actividades»: las tres, no una."""
    conceptos = ["PEDIR COTIZACION", "REVISAR ORDEN DE COMPRA", "SEGUIMIENTO A ENTREGA"]
    for i, concepto in enumerate(conceptos):
        res = work_order.process_and_save_work_order(
            [actividad(concepto, NOMBRE_DEL_DIRECTORIO, f"PPC-90001{i}")],
            "VANESSA_DE_LARA")
        assert res["success"] is True, res.get("message")

    assert sorted(hojas_con_tareas(motor).get(HOJA_DEL_TRACKER, [])) == sorted(conceptos)


def test_sin_responsable_la_actividad_sigue_yendo_a_administrador(motor) -> None:
    """`ADMINISTRADOR` es el destino de lo que no tiene dueño, y solo de eso."""
    work_order.process_and_save_work_order(
        [actividad("ACTIVIDAD SIN DUENO", "", "PPC-900100")], "VANESSA_DE_LARA")
    assert list(hojas_con_tareas(motor)) == [HOJA_PPC_POR_DEFECTO]


def test_un_responsable_fuera_del_organigrama_estrena_su_propia_hoja(motor) -> None:
    """
    Antes caía en `ADMINISTRADOR`, que es de las tareas sin responsable.

    Una persona con nombre y apellido no es "sin dueño": su actividad tiene que
    ir a su tracker, aunque sea el primero que se le crea.
    """
    work_order.process_and_save_work_order(
        [actividad("REVISAR PLANOS", "PERSONA NUEVA DEL EQUIPO", "PPC-900200")],
        "VANESSA_DE_LARA")
    assert list(hojas_con_tareas(motor)) == ["PERSONA NUEVA DEL EQUIPO"]


def test_una_tarea_que_ya_existe_no_cambia_de_hoja(motor) -> None:
    """La regla nueva no puede mover tareas que ya tienen dueño en la base."""
    motor.datos["tasks"].append(
        tarea_guardada("PPC-900300", "SONIA GARCIA PEREZ", "TAREA COMPARTIDA"))

    work_order.process_and_save_work_order(
        [actividad("TAREA COMPARTIDA", NOMBRE_DEL_DIRECTORIO, "PPC-900300")],
        "VANESSA_DE_LARA")

    assert list(hojas_con_tareas(motor)) == ["SONIA GARCIA PEREZ"]


# ---------------------------------------------------------------------------
# 3. Al leer: lo guardado con el otro nombre no se pierde
# ---------------------------------------------------------------------------

class FakeSupabase:
    """Doble de `sb_manager` con la forma que usa `sheets`."""

    def __init__(self, tasks):
        self._tasks = tasks

    def select(self, table, filters=None):
        filas = self._tasks if table == "tasks" else []
        if not filters:
            return list(filas)
        return [f for f in filas if all(f.get(k) == v for k, v in filters.items())]

    def select_in(self, table, column, values):
        filas = self._tasks if table == "tasks" else []
        return [f for f in filas if f.get(column) in list(values)]

    def select_distinct(self, table, column):
        vistos, salida = set(), []
        for f in (self._tasks if table == "tasks" else []):
            v = f.get(column)
            if v is not None and v not in vistos:
                vistos.add(v)
                salida.append({column: v})
        return salida

    def get_sheet_values(self, sheet_name):
        return []


@pytest.fixture
def lectura(monkeypatch):
    def instalar(tasks):
        doble = FakeSupabase(tasks)
        monkeypatch.setattr(sheets, "sb_manager", doble)
        monkeypatch.setattr(sheets.gs_manager, "is_mock", True, raising=False)
        sheets.reset_source_sheet_cache()
        return doble
    yield instalar
    sheets.reset_source_sheet_cache()


def _conceptos(valores) -> list:
    if not valores:
        return []
    columna = valores[0].index("CONCEPTO")
    return [fila[columna] for fila in valores[1:] if fila and any(fila)]


def test_su_tracker_muestra_lo_guardado_con_el_otro_nombre(lectura) -> None:
    """
    Las actividades que ya se archivaron mal tienen que reaparecer.

    Sin esto, el arreglo solo sirve para lo que se capture de hoy en adelante y
    lo anterior sigue perdido para ella.
    """
    lectura([
        tarea_guardada("PPC-1", NOMBRE_DEL_DIRECTORIO, "PEDIR COTIZACION"),
        tarea_guardada("VL-1", HOJA_DEL_TRACKER, "SEGUIMIENTO A ORDEN DE COMPRA"),
        tarea_guardada("SG-1", "SONIA GARCIA PEREZ", "TAREA DE OTRA PERSONA"),
    ])

    conceptos = _conceptos(sheets.gs_manager.get_sheet_values(HOJA_DEL_TRACKER))
    assert sorted(conceptos) == ["PEDIR COTIZACION", "SEGUIMIENTO A ORDEN DE COMPRA"], (
        "su tracker debe traer sus dos nombres, y solo los suyos"
    )


def test_el_tracker_de_otra_persona_no_se_contamina(lectura) -> None:
    lectura([
        tarea_guardada("PPC-1", NOMBRE_DEL_DIRECTORIO, "PEDIR COTIZACION"),
        tarea_guardada("SG-1", "SONIA GARCIA PEREZ", "TAREA DE OTRA PERSONA"),
    ])
    conceptos = _conceptos(sheets.gs_manager.get_sheet_values("SONIA GARCIA PEREZ"))
    assert conceptos == ["TAREA DE OTRA PERSONA"]


def test_una_hoja_de_una_sola_persona_se_lee_igual_que_antes(lectura) -> None:
    """Regresión: quien tiene un solo nombre no cambia de comportamiento."""
    lectura([tarea_guardada("SG-1", "SONIA GARCIA PEREZ", "REVISAR OC")])
    assert _conceptos(sheets.gs_manager.get_sheet_values("SONIA GARCIA PEREZ")) == ["REVISAR OC"]
