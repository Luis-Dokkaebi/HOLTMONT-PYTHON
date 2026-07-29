"""
Repositorio de `tasks`: lectura tipada y escritura transaccional.

Corre **sin base de datos**, sobre `MemoryEngine`, que reproduce a propósito
las tres cosas de Postgres de las que depende esta capa: el upsert que fusiona
en vez de reemplazar, el `NOT NULL` de `tasks.status` con su código `23502`, y
la reversión de la transacción.
"""

from __future__ import annotations

from datetime import time

import pytest
from pydantic import ValidationError

from backend.core.config import Settings
from backend.core.engines.memoria import MemoryEngine
from backend.core.errors import (
    ColumnaObligatoriaFaltante,
    ErrorDeMotor,
    EscrituraDeshabilitada,
)
from backend.repositories.tasks import TaskRepository, esta_archivada
from backend.schemas.task import (
    COLUMNAS_TASKS,
    NO_NULOS,
    OBLIGATORIAS_AL_INSERTAR,
    SOLO_LECTURA,
    TIPOS_REALES,
    TaskRead,
    TaskWrite,
)


def _settings(escritura: bool = True) -> Settings:
    return Settings(
        database_url=None,
        supabase_url=None,
        supabase_key=None,
        motor_forzado="memoria",
        escritura_habilitada=escritura,
    )


FILAS_SEMILLA = [
    {
        "id": "11111111-1111-1111-1111-111111111111",
        "dedupe_key": "JAIME OLIVO::JO-0009",
        "folio": "JO-0009",
        "source_sheet": "JAIME OLIVO",
        "concepto": "REVISAR PLANOS",
        "assignee_raw": "JAIME OLIVO",
        "avance": 45.0,
        "status": "ASIGNADO",
        "fecha_alta": "2026-03-01",
        "cumplimiento": "NO",
    },
    {
        "id": "22222222-2222-2222-2222-222222222222",
        "dedupe_key": "JAIME OLIVO::JO-0010",
        "folio": "JO-0010",
        "source_sheet": "JAIME OLIVO",
        "concepto": "ENTREGAR REPORTE",
        "avance": 100.0,
        "status": "HECHO",
        "cumplimiento": "SI",
    },
    {
        "id": "33333333-3333-3333-3333-333333333333",
        "dedupe_key": " LILIANA AYLIN MARTINEZ IBARRA::A-1",
        "folio": "A-1",
        # Hoja real con espacio inicial: la migración lo conservó.
        "source_sheet": " LILIANA AYLIN MARTINEZ IBARRA",
        "concepto": "COTIZAR",
        "avance": 1.0,
        "status": "PENDIENTE",
    },
]

PERSONAS = [
    {"id": "aaaa-1", "nombre": "JAIME OLIVO"},
    {"id": "aaaa-2", "nombre": "RAMIRO RODRIGUEZ"},
    {"id": "aaaa-3", "nombre": "ALFONSO CORREA"},
]


@pytest.fixture
def repo() -> TaskRepository:
    engine = MemoryEngine({"tasks": [dict(f) for f in FILAS_SEMILLA], "people": PERSONAS})
    return TaskRepository(engine, settings=_settings())


# --- Contrato del esquema ----------------------------------------------


def test_el_contrato_declara_las_28_columnas():
    assert len(COLUMNAS_TASKS) == 28, f"Se declararon {len(COLUMNAS_TASKS)} columnas, no 28"
    assert len(set(COLUMNAS_TASKS)) == 28, "Hay columnas repetidas en el contrato"


def test_el_modelo_de_lectura_cubre_todas_las_columnas():
    faltan = set(COLUMNAS_TASKS) - set(TaskRead.model_fields)
    assert not faltan, f"TaskRead no expone: {sorted(faltan)}"


def test_el_modelo_de_escritura_no_acepta_las_columnas_tecnicas():
    expuestas = set(TaskWrite.model_fields) - {"temp_id"}
    intrusas = expuestas & SOLO_LECTURA
    assert not intrusas, f"TaskWrite acepta columnas de solo lectura: {sorted(intrusas)}"


@pytest.mark.parametrize("campo", sorted(SOLO_LECTURA))
def test_el_cliente_no_puede_mandar_columnas_de_solo_lectura(campo):
    """
    Falla con 422 en vez de descartar en silencio.

    La lectura ya expone `id`, `dedupe_key` y `assignee_id`, así que un
    round-trip ingenuo del frontend las reenviaría; aceptarlas dejaría que el
    cliente reescriba la identidad de la fila.
    """
    with pytest.raises(ValidationError):
        TaskWrite(folio="JO-0009", **{campo: "lo-que-sea"})


# --- Tipos: lo que el adaptador de hoja destruía ------------------------


def test_la_lectura_preserva_los_tipos(repo):
    tarea = next(t for t in repo.listar("JAIME OLIVO") if t.folio == "JO-0009")
    assert isinstance(tarea.avance, float) and tarea.avance == 45.0
    assert tarea.fecha_alta is not None and tarea.fecha_alta.year == 2026
    assert isinstance(tarea.concepto, str)


def test_el_avance_cero_no_se_convierte_en_vacio(repo):
    """`str(0 or "")` daba "" y borraba el avance de 198 cotizaciones al 0 %."""
    repo.engine.datos["tasks"].append(
        {"dedupe_key": "JAIME OLIVO::JO-0011", "source_sheet": "JAIME OLIVO",
         "folio": "JO-0011", "avance": 0.0, "status": ""}
    )
    tarea = next(t for t in repo.listar("JAIME OLIVO") if t.folio == "JO-0011")
    assert tarea.avance == 0.0
    assert tarea.avance is not None


def test_el_numero_uno_y_el_string_uno_llegan_distintos_a_la_columna():
    assert TaskWrite(folio="X", avance=1).avance == 100.0
    assert TaskWrite(folio="X", avance="1").avance == 1.0


def test_una_fecha_corrupta_no_tumba_la_lectura_de_la_hoja():
    """Hay al menos una fila real cuyo rango arranca en el año 0202."""
    engine = MemoryEngine({"tasks": [
        {"dedupe_key": "H::1", "source_sheet": "H", "folio": "1",
         "fecha_alta": "0202-03-01", "status": "", "avance": None},
    ]})
    tareas = TaskRepository(engine, settings=_settings()).listar("H")
    assert len(tareas) == 1
    assert tareas[0].fecha_alta is None or tareas[0].fecha_alta.year == 202


# --- Resolución tolerante del nombre de hoja ---------------------------


def test_la_hoja_se_encuentra_sin_distinguir_mayusculas_ni_espacios(repo):
    """El frontend pide en mayúsculas; `source_sheet` no está normalizado."""
    assert repo.resolver_hoja("liliana aylin martinez ibarra") == " LILIANA AYLIN MARTINEZ IBARRA"
    assert repo.resolver_hoja("LILIANA AYLIN MARTINEZ IBARRA") == " LILIANA AYLIN MARTINEZ IBARRA"
    assert len(repo.listar("LILIANA AYLIN MARTINEZ IBARRA")) == 1


def test_una_hoja_desconocida_se_consulta_tal_cual_y_no_se_inventa(repo):
    assert repo.resolver_hoja("HOJA QUE NO EXISTE") == "HOJA QUE NO EXISTE"
    assert repo.listar("HOJA QUE NO EXISTE") == []


# --- Auto-archivado como estado calculado ------------------------------


def test_el_archivado_es_un_estado_calculado_no_una_posicion(repo):
    activas, archivadas = repo.particionar("JAIME OLIVO")
    assert {t.folio for t in activas} == {"JO-0009"}
    assert {t.folio for t in archivadas} == {"JO-0010"}


@pytest.mark.parametrize(
    "fila, archivada",
    [
        ({"avance": 100.0, "status": "", "cumplimiento": ""}, True),
        ({"avance": 45.0, "status": "HECHO", "cumplimiento": ""}, True),
        ({"avance": 45.0, "status": "", "cumplimiento": "SI"}, True),
        ({"avance": 45.0, "status": "ASIGNADO", "cumplimiento": "NO"}, False),
        ({"avance": None, "status": "", "cumplimiento": ""}, False),
    ],
)
def test_las_tres_condiciones_de_archivado(fila, archivada):
    assert esta_archivada(fila) is archivada


def test_una_tarea_al_uno_por_ciento_no_se_archiva(repo):
    """
    La trampa central de la Fase 1.

    Con la regla de la hoja (`is_progress_complete`), el número 1 vale 100 % y
    esta tarea se archivaría como terminada.
    """
    activas, archivadas = repo.particionar(" LILIANA AYLIN MARTINEZ IBARRA")
    assert [t.folio for t in activas] == ["A-1"]
    assert archivadas == []


# --- Escritura ----------------------------------------------------------


def test_la_escritura_esta_apagada_por_defecto_y_falla_ruidosamente():
    """
    Un `{success: true}` que no persiste es peor que un error: el frontend
    limpia el borrador y el usuario cree que guardó (lección de la Fase 0).
    """
    engine = MemoryEngine({"tasks": [], "people": []})
    repo = TaskRepository(engine, settings=_settings(escritura=False))
    with pytest.raises(EscrituraDeshabilitada):
        repo.guardar_lote("JAIME OLIVO", [TaskWrite(folio="JO-1", concepto="X", status="ASIGNADO")])
    assert engine.datos["tasks"] == []


def test_guardar_actualiza_la_fila_existente_en_vez_de_duplicarla(repo):
    antes = len(repo.engine.datos["tasks"])
    repo.guardar_lote("JAIME OLIVO", [TaskWrite(folio="JO-0009", avance="80")])
    assert len(repo.engine.datos["tasks"]) == antes, "Se insertó un duplicado"
    fila = next(f for f in repo.engine.datos["tasks"] if f["folio"] == "JO-0009")
    assert fila["avance"] == 80.0


def test_el_upsert_no_borra_las_columnas_que_no_se_mandaron(repo):
    """`merge-duplicates`: una columna ausente conserva lo que ya había."""
    repo.guardar_lote("JAIME OLIVO", [TaskWrite(folio="JO-0009", avance="80")])
    fila = next(f for f in repo.engine.datos["tasks"] if f["folio"] == "JO-0009")
    assert fila["concepto"] == "REVISAR PLANOS"
    assert fila["status"] == "ASIGNADO"


def test_el_mismo_folio_en_dos_hojas_son_dos_filas(repo):
    """382 folios viven en más de una fila por difusión lateral. No colapsarlos."""
    repo.guardar_lote("TERESA GARZA", [TaskWrite(folio="JO-0009", concepto="COPIA", status="ASIGNADO")])
    claves = {f["dedupe_key"] for f in repo.engine.datos["tasks"]}
    assert "JAIME OLIVO::JO-0009" in claves
    assert "TERESA GARZA::JO-0009" in claves


def test_el_estatus_se_normaliza_al_escribir(repo):
    """Que la columna no vuelva a acumular 45 variantes de 11 estatus."""
    repo.guardar_lote("JAIME OLIVO", [TaskWrite(folio="JO-0009", status="ASIGANDA")])
    fila = next(f for f in repo.engine.datos["tasks"] if f["folio"] == "JO-0009")
    assert fila["status"] == "ASIGNADO"


def test_un_estatus_desconocido_se_conserva_tal_cual(repo):
    """Tirarlo en silencio perdería el dato si el equipo empieza a usar uno nuevo."""
    repo.guardar_lote("JAIME OLIVO", [TaskWrite(folio="JO-0009", status="EN LICITACION")])
    fila = next(f for f in repo.engine.datos["tasks"] if f["folio"] == "JO-0009")
    assert fila["status"] == "EN LICITACION"


def test_nunca_se_escribe_nulo_en_status(repo):
    """`tasks.status` es NOT NULL: el nulo aborta el upsert con 23502."""
    repo.guardar_lote("JAIME OLIVO", [TaskWrite(folio="JO-0009", status=None)])
    fila = next(f for f in repo.engine.datos["tasks"] if f["folio"] == "JO-0009")
    assert fila["status"] is not None


def test_el_motor_reproduce_la_restriccion_not_null():
    engine = MemoryEngine({"tasks": []})
    with pytest.raises(ErrorDeMotor) as exc:
        engine.upsert("tasks", [{"dedupe_key": "H::1", "status": None}], en_conflicto="dedupe_key")
    assert exc.value.codigo == "23502"


def test_el_assignee_id_toma_la_primera_persona(repo):
    """Nunca guardar el compuesto: ya ensució `people` con filas de dos nombres."""
    repo.guardar_lote(
        "JAIME OLIVO",
        [TaskWrite(folio="JO-0009", assignee_raw="RAMIRO RODRIGUEZ, ALFONSO CORREA")],
    )
    fila = next(f for f in repo.engine.datos["tasks"] if f["folio"] == "JO-0009")
    assert fila["assignee_id"] == "aaaa-2"


def test_una_fila_sin_folio_no_se_escribe(repo):
    antes = len(repo.engine.datos["tasks"])
    assert repo.guardar_lote("JAIME OLIVO", [TaskWrite(concepto="SIN FOLIO")]) == []
    assert len(repo.engine.datos["tasks"]) == antes


def test_el_source_sheet_lo_pone_el_servidor_no_el_cliente(repo):
    repo.guardar_lote("TERESA GARZA", [TaskWrite(folio="TG-9", concepto="X")])
    fila = next(f for f in repo.engine.datos["tasks"] if f["folio"] == "TG-9")
    assert fila["source_sheet"] == "TERESA GARZA"


# --- Transacción --------------------------------------------------------


def test_el_lote_es_transaccional_y_no_deja_nada_a_medias():
    """Hoy no hay transacciones: media escritura es el estado más caro posible."""
    engine = MemoryEngine({"tasks": [dict(f) for f in FILAS_SEMILLA], "people": PERSONAS})
    repo = TaskRepository(engine, settings=_settings())
    antes = [dict(f) for f in engine.datos["tasks"]]

    original = engine.upsert
    llamadas = {"n": 0}

    def upsert_que_falla_a_la_segunda(*args, **kwargs):
        llamadas["n"] += 1
        if llamadas["n"] == 2:
            raise ErrorDeMotor("fallo simulado a mitad del lote")
        return original(*args, **kwargs)

    engine.upsert = upsert_que_falla_a_la_segunda
    with pytest.raises(ErrorDeMotor):
        repo.guardar_lote(
            "JAIME OLIVO",
            [
                TaskWrite(folio="JO-0009", avance="80"),
                TaskWrite(folio="JO-0012", concepto="NUEVA"),
            ],
        )
    assert engine.datos["tasks"] == antes, "La transacción no revirtió el lote"


def test_las_filas_se_agrupan_por_conjunto_de_columnas():
    """
    PostgREST exige que todos los objetos de un arreglo tengan las mismas
    claves, y rellenar las que faltan con nulo borraría datos en la base.
    """
    engine = MemoryEngine({"tasks": [], "people": []})
    repo = TaskRepository(engine, settings=_settings())
    lotes = []
    original = engine.upsert

    def espiar(tabla, filas, **kwargs):
        lotes.append([set(f.keys()) for f in filas])
        return original(tabla, filas, **kwargs)

    engine.upsert = espiar
    repo.guardar_lote(
        "H",
        [
            TaskWrite(folio="A-1", concepto="X", status="ASIGNADO"),
            TaskWrite(folio="A-2", concepto="Y", status="ASIGNADO"),
            TaskWrite(folio="A-3", concepto="Z", avance="50"),
        ],
    )
    assert len(lotes) == 2, "Se esperaban dos grupos de columnas distintas"
    for lote in lotes:
        assert len(set(map(frozenset, lote))) == 1, "Un lote mezcla filas con columnas distintas"


# --- Las nueve columnas NOT NULL ---------------------------------------


def test_el_contrato_declara_las_nueve_columnas_not_null():
    """El documento de partida solo mencionaba `status`. Son nueve."""
    assert NO_NULOS == {
        "id", "folio", "dedupe_key", "folio_sintetico", "concepto",
        "avance", "status", "source_sheet", "created_at",
    }
    assert NO_NULOS <= set(COLUMNAS_TASKS)


def test_las_obligatorias_al_insertar_son_las_que_no_tienen_default():
    """`id`, `folio_sintetico`, `avance`, `status` y `created_at` sí lo tienen."""
    assert OBLIGATORIAS_AL_INSERTAR == {"folio", "dedupe_key", "concepto", "source_sheet"}
    assert OBLIGATORIAS_AL_INSERTAR < NO_NULOS


def test_no_se_puede_dar_de_alta_una_tarea_sin_concepto(repo):
    """`concepto` es NOT NULL y no tiene default: el alta abortaría con 23502."""
    with pytest.raises(ColumnaObligatoriaFaltante) as exc:
        repo.guardar_lote("JAIME OLIVO", [TaskWrite(folio="JO-NUEVA", avance="10")])
    assert "concepto" in str(exc.value)
    assert "JO-NUEVA" in str(exc.value)


def test_actualizar_una_tarea_existente_no_exige_concepto(repo):
    """En el merge, la columna ausente conserva lo que ya está en la base."""
    guardadas = repo.guardar_lote("JAIME OLIVO", [TaskWrite(folio="JO-0009", avance="70")])
    assert guardadas[0].avance == 70.0
    assert guardadas[0].concepto == "REVISAR PLANOS"


def test_un_avance_vacio_se_omite_en_vez_de_mandar_nulo(repo):
    """
    `avance` es NOT NULL con DEFAULT 0. Mandar nulo aborta el upsert; escribir
    un 0 fabricaría un "0 %" que nadie capturó.
    """
    repo.guardar_lote("JAIME OLIVO", [TaskWrite(folio="JO-0009", avance=None, comentarios="X")])
    fila = next(f for f in repo.engine.datos["tasks"] if f["folio"] == "JO-0009")
    assert fila["avance"] == 45.0, "Se pisó el avance existente"


def test_el_alta_toma_los_valores_por_defecto_de_la_base(repo):
    """Omitir `status` o `avance` en un alta no falla: la base pone su default."""
    repo.guardar_lote("JAIME OLIVO", [TaskWrite(folio="JO-NUEVA", concepto="ALTA LIMPIA")])
    fila = next(f for f in repo.engine.datos["tasks"] if f["folio"] == "JO-NUEVA")
    assert fila["status"] == "PENDIENTE"
    assert fila["avance"] == 0
    assert fila["folio_sintetico"] is False


def test_el_motor_rechaza_un_alta_sin_columna_obligatoria():
    engine = MemoryEngine({"tasks": []})
    with pytest.raises(ErrorDeMotor) as exc:
        engine.upsert(
            "tasks",
            [{"dedupe_key": "H::1", "folio": "1", "source_sheet": "H"}],  # sin concepto
            en_conflicto="dedupe_key",
        )
    assert exc.value.codigo == "23502"


# --- Tipos verificados contra el esquema real ---------------------------


def test_los_tipos_declarados_cubren_las_28_columnas():
    assert set(TIPOS_REALES) == set(COLUMNAS_TASKS)


def test_folio_sintetico_es_booleano_no_texto():
    """Se había deducido como texto sin evidencia; el esquema dice boolean."""
    assert TIPOS_REALES["folio_sintetico"] == "boolean"
    tarea = TaskRead.model_validate(
        {"dedupe_key": "H::1", "folio": "H::ROW1604", "folio_sintetico": True}
    )
    assert tarea.folio_sintetico is True


def test_las_horas_son_time_no_texto():
    assert TIPOS_REALES["hora_alta"] == "time without time zone"
    tarea = TaskRead.model_validate({"hora_alta": "13:55:00", "hora_estimada_fin": "17:33:00"})
    assert tarea.hora_alta == time(13, 55)
    assert tarea.hora_estimada_fin == time(17, 33)


def test_correo_no_se_acepta_del_cliente():
    """
    La columna se llama `correo` pero no contiene ni una dirección: sus 2.266
    valores son enlaces de Drive y de Sheets, igual que `carpeta`. Es una
    columna de archivos mal nombrada por la migración, y los archivos quedan
    fuera del alcance de esta fase.
    """
    assert "correo" in SOLO_LECTURA
    assert "correo" not in TaskWrite.model_fields
    assert "correo" in TaskRead.model_fields


# --- Router /api/v2 -----------------------------------------------------


@pytest.fixture
def cliente(repo):
    """La app real, con el repositorio en memoria inyectado por dependencia."""
    from fastapi.testclient import TestClient

    from api.main import app
    from backend.routers.tasks import obtener_repositorio

    app.dependency_overrides[obtener_repositorio] = lambda: repo
    try:
        yield TestClient(app)
    finally:
        app.dependency_overrides.clear()


def test_la_lectura_devuelve_data_e_history_como_espera_el_frontend(cliente):
    respuesta = cliente.get("/api/v2/tasks", params={"sheet": "jaime olivo"})
    assert respuesta.status_code == 200
    cuerpo = respuesta.json()
    assert cuerpo["success"] is True
    assert [t["folio"] for t in cuerpo["data"]] == ["JO-0009"]
    assert [t["folio"] for t in cuerpo["history"]] == ["JO-0010"]
    # El avance viaja como número, no como texto.
    assert cuerpo["data"][0]["avance"] == 45.0


def test_el_endpoint_rechaza_las_columnas_de_solo_lectura(cliente):
    respuesta = cliente.post(
        "/api/v2/tasks/batch",
        json={"sheetName": "JAIME OLIVO", "tasks": [{"folio": "JO-0009", "dedupe_key": "otra"}]},
    )
    assert respuesta.status_code == 422


def test_el_endpoint_guarda_y_devuelve_la_fila_actualizada(cliente):
    respuesta = cliente.post(
        "/api/v2/tasks/batch",
        json={"sheetName": "JAIME OLIVO", "tasks": [{"folio": "JO-0009", "avance": "80"}]},
    )
    assert respuesta.status_code == 200
    assert respuesta.json()["data"][0]["avance"] == 80.0


def test_el_endpoint_avisa_con_503_si_la_escritura_esta_apagada(repo):
    from fastapi.testclient import TestClient

    from api.main import app
    from backend.routers.tasks import obtener_repositorio

    repo.settings = _settings(escritura=False)
    app.dependency_overrides[obtener_repositorio] = lambda: repo
    try:
        respuesta = TestClient(app).post(
            "/api/v2/tasks/batch",
            json={"sheetName": "JAIME OLIVO", "tasks": [{"folio": "JO-0009"}]},
        )
    finally:
        app.dependency_overrides.clear()
    assert respuesta.status_code == 503
    # El interruptor ya no arranca apagado (la base es la fuente de verdad),
    # pero sigue existiendo como parada de emergencia y tiene que decir cuál es
    # y cómo se quita, no fallar con un mensaje genérico.
    assert "BACKEND_TASKS_WRITE_ENABLED" in respuesta.json()["detail"]
