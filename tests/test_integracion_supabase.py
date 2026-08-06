"""
Integración con la base: cada usuario escribe en su propia partición.

Lo que se comprueba aquí es el camino que usa la aplicación de verdad
(`index.html` -> `api_service.js` -> `/api/legacy/saveTrackerBatch`), que hasta
ahora terminaba en `GSheetsManager.write_values` y, sin `credentials.json`, en
un diccionario en memoria que muere con la invocación.

Corre sobre `MemoryEngine`, sin base de datos. Las tres cosas de Postgres de
las que depende esta capa —el upsert que fusiona, el `NOT NULL` con su código
`23502` y la reversión de la transacción— están reproducidas ahí.
"""

from __future__ import annotations

from datetime import date, time

import pytest

from api.services import tracker_store
from api.services.sheets import _valores_de_tareas
from backend.core.engines.memoria import MemoryEngine
from backend.core.errors import ErrorDeMotor
from backend.repositories.quotes import QuoteRepository
from backend.repositories.tasks import TaskRepository
from backend.schemas.quote import QuoteWrite
from backend.schemas.task import TaskWrite
from backend.services import auditoria
from backend.services.persistencia import PersistenciaTracker


# ----------------------------------------------------------------------
# Traducción hoja -> columnas
# ----------------------------------------------------------------------

def test_los_encabezados_de_hoja_se_traducen_a_columnas():
    tarea = TaskWrite.desde_hoja({
        "FOLIO": "JO-0009",
        "CONCEPTO": "REVISAR PLANOS",
        "RESPONSABLE": "JAIME OLIVO",
        "AREA": "CONSTRUCCION",
        "ESTATUS": "ASIGNADO",
        # Metadatos del frontend y columnas que `tasks` no tiene: se descartan
        # en vez de estrellarse contra el `extra="forbid"` del modelo.
        "_tempId": "tmp-1",
        "_rowIndex": 12,
        "CLIENTE": "ACME",
    })
    columnas = tarea.columnas()
    assert columnas["folio"] == "JO-0009"
    assert columnas["assignee_raw"] == "JAIME OLIVO"
    assert columnas["departamento"] == "CONSTRUCCION"
    assert columnas["status"] == "ASIGNADO"
    assert "temp_id" not in columnas and "cliente" not in columnas
    assert tarea.temp_id == "tmp-1"


def test_las_fechas_y_horas_de_la_hoja_se_convierten():
    """`index.html` manda `dd/mm/yy`, que Pydantic no sabe leer por su cuenta."""
    tarea = TaskWrite.desde_hoja({
        "FOLIO": "JO-1", "FECHA": "27/07/26", "HORA ALTA": "09:15",
        "FECHA_RESPUESTA": "2026-08-01",
    })
    assert tarea.fecha_alta == date(2026, 7, 27)
    assert tarea.hora_alta == time(9, 15)
    assert tarea.fecha_respuesta == date(2026, 8, 1)


def test_el_numero_1_y_el_string_1_siguen_significando_cosas_distintas():
    """AGENTS.md §4: la celda porcentual `1` es 100 %; el `"1"` tecleado es 1 %."""
    assert TaskWrite.desde_hoja({"AVANCE": 1}).avance == 100.0
    assert TaskWrite.desde_hoja({"AVANCE": "1"}).avance == 1.0


def test_los_encabezados_con_punto_y_acento_tambien_casan():
    cotizacion = QuoteWrite.desde_hoja({
        "FOLIO": "AV-1", "F. VISITA": "01/03/26", "PRIO. COT.": "ALTA",
        "MONTO": "$ 1,250.50", "DÍAS": "7", "COTIZACIÓN": "COT-9",
    })
    assert cotizacion.f_visita == date(2026, 3, 1)
    assert cotizacion.prioridad_cot == "ALTA"
    assert cotizacion.monto == 1250.5
    assert cotizacion.dias == 7
    assert cotizacion.cotizacion == "COT-9"


# ----------------------------------------------------------------------
# Repositorios
# ----------------------------------------------------------------------

SEMILLA_TASKS = [
    {
        "id": "11111111-1111-1111-1111-111111111111",
        "dedupe_key": "JAIME OLIVO::JO-0009",
        "folio": "JO-0009",
        "source_sheet": "JAIME OLIVO",
        "concepto": "REVISAR PLANOS",
        "assignee_raw": "JAIME OLIVO",
        "avance": 45.0,
        "status": "ASIGNADO",
    },
    {
        # Folio de secuencia global: su clave es el folio a secas, así que esta
        # es su ÚNICA fila en toda la base.
        "id": "22222222-2222-2222-2222-222222222222",
        "dedupe_key": "PPC-500",
        "folio": "PPC-500",
        "source_sheet": "ADMINISTRADOR",
        "concepto": "COMPRA DE MATERIAL",
        "assignee_raw": "VANESSA DE LARA",
        "avance": 0.0,
        "status": "PENDIENTE",
    },
]

SEMILLA_QUOTES = [
    {
        "folio": "AV-0100",
        "source_sheet": "Sebastian Padilla (VENTAS)",
        "cliente": "ACME",
        "concepto": "COTIZAR NAVE",
        "avance": 20.0,
        "estatus": "EN PROCESO",
    },
]

SEMILLA_PEOPLE = [
    {"id": "p-1", "nombre": "JAIME OLIVO"},
    {"id": "p-2", "nombre": "VANESSA DE LARA"},
    {"id": "p-3", "nombre": "SEBASTIAN PADILLA"},
]


@pytest.fixture
def motor():
    return MemoryEngine({
        "tasks": [dict(f) for f in SEMILLA_TASKS],
        "quotes": [dict(f) for f in SEMILLA_QUOTES],
        "people": [dict(f) for f in SEMILLA_PEOPLE],
        "plan_semanal": [],
        "task_involucrados": [],
        "system_log": [],
    })


def test_una_actualizacion_parcial_conserva_las_columnas_not_null(motor):
    """
    El upsert de PostgREST es un `INSERT ... ON CONFLICT`, y Postgres valida el
    NOT NULL sobre la tupla del INSERT *antes* de resolver el conflicto. Sin
    completar `folio`, `concepto` y `source_sheet` desde la fila almacenada,
    guardar solo el avance devolvía un 23502.
    """
    repo = TaskRepository(motor)
    guardadas = repo.guardar_lote("JAIME OLIVO", [TaskWrite.desde_hoja(
        {"FOLIO": "JO-0009", "AVANCE": "80"}
    )])

    assert guardadas[0].avance == 80.0
    assert guardadas[0].concepto == "REVISAR PLANOS", "el merge no puede borrar el concepto"
    assert len(motor.select("tasks")) == 2, "debe actualizar, no insertar un duplicado"


def test_una_tarea_existente_no_cambia_de_dueno(motor):
    """
    `PPC-500` vive en `ADMINISTRADOR`. Guardarla desde otra vista no puede
    llevársela: con folio global hay una sola fila en toda la base.
    """
    repo = TaskRepository(motor)
    repo.guardar_lote("JAIME OLIVO", [TaskWrite.desde_hoja(
        {"FOLIO": "PPC-500", "AVANCE": "30"}
    )])

    fila = [f for f in motor.select("tasks") if f["folio"] == "PPC-500"][0]
    assert fila["source_sheet"] == "ADMINISTRADOR"
    assert fila["avance"] == 30.0


def test_una_tarea_nueva_cae_en_la_particion_de_su_hoja(motor):
    repo = TaskRepository(motor)
    repo.guardar_lote("VANESSA DE LARA", [TaskWrite.desde_hoja(
        {"FOLIO": "VD-0001", "CONCEPTO": "PEDIR COTIZACIONES", "RESPONSABLE": "VANESSA DE LARA"}
    )])

    fila = [f for f in motor.select("tasks") if f["folio"] == "VD-0001"][0]
    assert fila["source_sheet"] == "VANESSA DE LARA"
    assert fila["dedupe_key"] == "VANESSA DE LARA::VD-0001"
    assert fila["assignee_id"] == "p-2"


def test_el_reverse_sync_no_le_roba_la_cotizacion_a_su_vendedor(motor):
    """
    Sincronizar hacia la hoja de Toñita no puede mover la fila del vendedor.

    El invariante es el mismo de siempre; lo que cambió es cómo se cumple.
    Cuando `quotes` tenía `folio` como clave primaria había una sola fila en
    toda la base, y la defensa era congelar `source_sheet` para que un guardado
    desde otra vista no se la llevara. Desde que la identidad es
    `(folio, source_sheet)` cada hoja tiene su propia fila, así que la de
    Sebastián sencillamente no se toca: escribir en la de Antonia es escribir en
    otra fila.

    Se comprueba lo uno **y** lo otro —que la suya queda intacta y que la de
    Antonia recibe los valores nuevos—, que es más de lo que verificaba la
    versión anterior.
    """
    repo = QuoteRepository(motor)
    repo.guardar_lote("ANTONIA_VENTAS", [QuoteWrite.desde_hoja(
        {"FOLIO": "AV-0100", "AVANCE": "60", "ESTATUS": "ENVIADA",
         "CLIENTE": "ACME", "CONCEPTO": "COTIZAR NAVE"}
    )])

    por_hoja = {f["source_sheet"]: f for f in motor.select("quotes")
                if f["folio"] == "AV-0100"}
    assert sorted(por_hoja) == ["ANTONIA_VENTAS", "Sebastian Padilla (VENTAS)"]

    del_vendedor = por_hoja["Sebastian Padilla (VENTAS)"]
    assert del_vendedor["avance"] == 20.0, "la fila del vendedor no se toca"
    assert del_vendedor["estatus"] == "EN PROCESO"

    de_antonia = por_hoja["ANTONIA_VENTAS"]
    assert de_antonia["avance"] == 60.0
    assert de_antonia["estatus"] == "ENVIADA"
    assert de_antonia["cliente"] == "ACME"


# ----------------------------------------------------------------------
# Puente de persistencia
# ----------------------------------------------------------------------

def test_las_hojas_de_ventas_van_a_quotes_y_el_resto_a_tasks(motor):
    puente = PersistenciaTracker(motor)

    de_ventas = puente.guardar("ANTONIA_VENTAS", [
        {"FOLIO": "AV-0200", "CLIENTE": "NIDEC", "CONCEPTO": "COTIZAR"}
    ])
    de_tareas = puente.guardar("JAIME OLIVO", [
        {"FOLIO": "JO-0010", "CONCEPTO": "SUPERVISAR"}
    ])

    assert de_ventas.tabla == "quotes" and de_ventas.exito
    assert de_tareas.tabla == "tasks" and de_tareas.exito
    assert {f["folio"] for f in motor.select("quotes")} == {"AV-0100", "AV-0200"}
    assert motor.select("quotes", donde={"folio": "AV-0200"})[0]["source_sheet"] == "ANTONIA_VENTAS"


def test_la_hoja_se_resuelve_aunque_venga_con_otra_grafia(motor):
    """
    `source_sheet` no está normalizado: hay hojas con capitalización mixta y
    una con espacio inicial. El frontend las pide en mayúsculas.
    """
    motor.datos["tasks"].append({
        "id": "33333333-3333-3333-3333-333333333333",
        "dedupe_key": " LILIANA AYLIN MARTINEZ IBARRA::LM-1",
        "folio": "LM-1", "source_sheet": " LILIANA AYLIN MARTINEZ IBARRA",
        "concepto": "X", "avance": 0.0, "status": "PENDIENTE",
    })
    puente = PersistenciaTracker(motor)
    assert puente.resolver_hoja("liliana aylin martinez ibarra") == " LILIANA AYLIN MARTINEZ IBARRA"
    assert puente.resolver_hoja("SEBASTIAN PADILLA (VENTAS)") == "Sebastian Padilla (VENTAS)"


def test_lo_capturado_en_el_ppc_maestro_va_a_la_hoja_de_su_responsable(motor):
    """
    `PPCV3` no es una partición sino un índice en `plan_semanal` (§7.7 del
    plan). Escribir con `source_sheet='PPCV3'` estrenaría una hoja que la vista
    de Planeación Semanal no lee.
    """
    puente = PersistenciaTracker(motor)
    resultado = puente.guardar("PPCV3", [
        {"FOLIO": "PPC-900", "CONCEPTO": "NUEVA DEL PPC", "RESPONSABLE": "JAIME OLIVO"}
    ])

    assert resultado.exito
    fila = [f for f in motor.select("tasks") if f["folio"] == "PPC-900"][0]
    assert fila["source_sheet"] == "JAIME OLIVO"
    assert not [f for f in motor.select("tasks") if f["source_sheet"] == "PPCV3"]
    indice = motor.select("plan_semanal", donde={"source_sheet": "PPCV3"})
    assert [f["task_folio"] for f in indice] == ["PPC-900"]


def test_actualizar_desde_el_ppc_maestro_encuentra_la_tarea_donde_este(motor):
    puente = PersistenciaTracker(motor)
    puente.guardar("PPCV3", [{"FOLIO": "PPC-500", "AVANCE": "70"}])

    fila = [f for f in motor.select("tasks") if f["folio"] == "PPC-500"][0]
    assert fila["source_sheet"] == "ADMINISTRADOR"
    assert fila["avance"] == 70.0


def test_los_involucrados_se_proyectan_desde_el_string(motor):
    """Decisión D: la fuente de verdad es el string; la tabla es derivada."""
    puente = PersistenciaTracker(motor)
    puente.guardar("JAIME OLIVO", [{
        "FOLIO": "JO-0011", "CONCEPTO": "COORDINAR",
        "INVOLUCRADOS": "JAIME OLIVO, VANESSA DE LARA",
    }])

    proyectados = {(f["raw_name"], f["person_id"]) for f in motor.select("task_involucrados")}
    assert proyectados == {("JAIME OLIVO", "p-1"), ("VANESSA DE LARA", "p-2")}


# ----------------------------------------------------------------------
# Consecutivos de folio
# ----------------------------------------------------------------------

def test_el_consecutivo_global_mira_toda_la_tabla(motor):
    """
    Un prefijo de secuencia global identifica la fila por sí solo, así que el
    consecutivo tiene que salir de toda la tabla. En la base hay 25 folios
    `AV-` en hojas de vendedores, no en la maestra: mirar solo `ANTONIA_VENTAS`
    generaría un folio ya usado y el upsert pisaría la cotización de otro.
    """
    motor.datos["quotes"].append({
        "folio": "AV-3250", "source_sheet": "TERESA GARZA (VENTAS)", "avance": 0.0,
    })
    puente = PersistenciaTracker(motor)
    assert puente.ultimo_consecutivo("AV-", "ANTONIA_VENTAS") == 3250


def test_el_consecutivo_de_iniciales_es_por_hoja(motor):
    """`JO-0009` solo es único dentro de su hoja: eso permite la papa caliente."""
    motor.datos["tasks"].append({
        "id": "44444444-4444-4444-4444-444444444444",
        "dedupe_key": "OTRA HOJA::JO-7000", "folio": "JO-7000",
        "source_sheet": "OTRA HOJA", "concepto": "X", "avance": 0.0, "status": "PENDIENTE",
    })
    puente = PersistenciaTracker(motor)
    assert puente.ultimo_consecutivo("JO-", "JAIME OLIVO") == 1000
    assert puente.ultimo_consecutivo("JO-", "OTRA HOJA") == 7000


# ----------------------------------------------------------------------
# Camino vivo: /api/legacy/saveTrackerBatch
# ----------------------------------------------------------------------

@pytest.fixture
def tracker(monkeypatch, motor):
    """`tracker_store` escribiendo contra el motor en memoria."""
    monkeypatch.setattr(tracker_store, "_persistencia", lambda: PersistenciaTracker(motor))
    # La lectura de la matriz sigue siendo la del adaptador de hojas; aquí se
    # fija para que la prueba no dependa de credenciales.
    monkeypatch.setattr(
        tracker_store, "read_values",
        lambda hoja: [["FOLIO", "CONCEPTO", "RESPONSABLE", "FECHA", "AVANCE", "ESTATUS"]],
    )
    return motor


def test_guardar_desde_el_tracker_persiste_en_la_hoja_del_usuario(tracker):
    respuesta = tracker_store.save_tracker_batch(
        "VANESSA DE LARA",
        [{"FOLIO": "VD-0500", "CONCEPTO": "REVISAR OC", "RESPONSABLE": "VANESSA DE LARA",
          "AVANCE": "0", "ESTATUS": "ASIGNADO", "_tempId": "tmp-9"}],
        username="VANESSA_DE_LARA",
    )

    assert respuesta["success"] is True
    fila = [f for f in tracker.select("tasks") if f["folio"] == "VD-0500"][0]
    assert fila["source_sheet"] == "VANESSA DE LARA"
    assert fila["concepto"] == "REVISAR OC"

    eventos = tracker.select("system_log")
    assert eventos and eventos[0]["accion"] == "ACTUALIZAR"
    assert "VD-0500" in eventos[0]["detalles"]
    assert eventos[0]["usuario"] == "VANESSA_DE_LARA"


def test_dos_altas_sin_folio_no_se_pisan_entre_invocaciones(tracker):
    """
    El proveedor de secuencias de `tracker_rules` es un contador en memoria del
    proceso. En serverless cada invocación empieza de cero, así que devolvía
    `1001` siempre: la segunda tarea sin folio recibía el mismo que la primera
    y el upsert la sobrescribía. El consecutivo sale ahora de la base.
    """
    for i in (1, 2):
        respuesta = tracker_store.save_tracker_batch(
            "JAIME OLIVO",
            [{"CONCEPTO": f"TAREA {i}", "RESPONSABLE": "JAIME OLIVO", "_tempId": f"t{i}"}],
            username="JAIME_OLIVO",
        )
        assert respuesta["success"] is True, respuesta.get("message")

    folios = sorted(f["folio"] for f in tracker.select("tasks", donde={"source_sheet": "JAIME OLIVO"}))
    assert folios == ["JO-0009", "JO-1001", "JO-1002"]


def test_un_fallo_al_escribir_no_se_reporta_como_guardado(tracker, monkeypatch):
    """
    La mentira que erradicó la Fase 0: con `success: true` el frontend marca
    `_isNew = false` y borra el borrador local del usuario.
    """
    def revienta(*_a, **_k):
        raise ErrorDeMotor("permiso denegado")

    monkeypatch.setattr(tracker, "upsert", revienta)

    respuesta = tracker_store.save_tracker_batch(
        "VANESSA DE LARA",
        [{"FOLIO": "VD-0501", "CONCEPTO": "NO DEBE GUARDARSE"}],
        username="VANESSA_DE_LARA",
    )

    assert respuesta["success"] is False
    assert "permiso denegado" in respuesta["message"]


def test_el_cambio_de_fecha_se_audita_en_system_log(monkeypatch, motor):
    monkeypatch.setattr(auditoria, "construir_engine", lambda *a, **k: motor)

    respuesta = tracker_store.log_date_change(
        {"hoja": "ANTONIA_VENTAS", "folio": "AV-0100", "campo": "F. ENTREGA",
         "anterior": "01/03/26", "nuevo": "15/03/26"},
        username="ANTONIA_VENTAS",
    )

    assert respuesta["success"] is True and respuesta["logged"] is True
    evento = motor.select("system_log")[0]
    assert evento["accion"] == "CAMBIO_FECHA"
    assert "AV-0100" in evento["detalles"] and "15/03/26" in evento["detalles"]


# ----------------------------------------------------------------------
# Lectura: el separador de archivadas
# ----------------------------------------------------------------------

def test_al_leer_se_reconstruye_el_separador_de_tareas_realizadas():
    """
    En la hoja, las terminadas viven debajo de "TAREAS REALIZADAS" y
    `apiFetchStaffTrackerData` corta ahí. En la base no hay filas "debajo" de
    nada, así que la partición se calcula y el separador se reconstruye.
    """
    filas = [
        {"folio": "A-1", "concepto": "ACTIVA", "avance": 45.0, "status": "ASIGNADO"},
        {"folio": "A-2", "concepto": "TERMINADA POR AVANCE", "avance": 100.0, "status": "ASIGNADO"},
        {"folio": "A-3", "concepto": "TERMINADA POR ESTATUS", "avance": 10.0, "status": "HECHO"},
        {"folio": "A-4", "concepto": "TERMINADA POR CUMPLIMIENTO", "avance": 0.0,
         "status": "ASIGNADO", "cumplimiento": "SI"},
    ]
    valores = _valores_de_tareas(filas)
    texto = ["|".join(str(c) for c in fila) for fila in valores]

    corte = next(i for i, fila in enumerate(texto) if "TAREAS REALIZADAS" in fila)
    assert "ACTIVA" in texto[1] and corte == 2, "solo A-1 queda activa"
    assert len(valores) - corte - 1 == 3, "las otras tres quedan archivadas"


def test_el_avance_1_no_archiva_la_tarea():
    """
    En la base `avance` ya está en escala 0-100, así que `1` es 1 %. Aplicar
    ahí la regla de la hoja archivaría como terminada una tarea al 1 %.
    """
    valores = _valores_de_tareas([
        {"folio": "A-1", "concepto": "APENAS EMPEZADA", "avance": 1.0, "status": "ASIGNADO"},
    ])
    assert not any("TAREAS REALIZADAS" in "|".join(str(c) for c in f) for f in valores)
