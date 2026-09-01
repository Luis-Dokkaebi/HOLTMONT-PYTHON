"""
La clave primaria de Postgres no es un folio.

Reporte del dueño (BUG-0016, ANTONIA_VENTAS, 2026-08-24): «Se duplicaron las
tareas marcadas en amarillo, ya las había cerrado pero volvieron a aparecer».
En la captura que acompaña al ticket, cada actividad aparece **dos veces** en la
misma tabla y con el mismo CONCEPTO, FECHA, HORA e INVOLUCRADOS. Lo único que
las distingue es la primera columna:

    8   B90ED1A7-7C   2026-07-21  13:22  PROYECTO 3459 REUBICACION DE PUERTA
    9   DD138CA1-A3   2026-07-21  12:39  PREFACTURA 10295 POLIZA AGOSTO 2026
    10  RC-0162       2026-07-21  12:39  PREFACTURA 10295 POLIZA AGOSTO 2026
    11  RC-0170       2026-07-21  13:22  PROYECTO 3459 REUBICACION DE PUERTA

`B90ED1A7-7C` no es un folio: es el principio de `tasks.id`, el UUID que genera
Postgres. La lectura lo expone al frontend como una columna más —`ID`, oculta en
la vista pero presente en la fila—, y el frontend lo devuelve intacto en cada
guardado.

La cadena, medida y reproducida en `test_asi_se_duplicaba_la_actividad`:

  1. `COLUMN_ALIASES` del puerto a Python declara `"FOLIO": ["FOLIO", "ID"]`.
     `CODIGO.js:1106-1131` **no tiene esa entrada**: su diccionario de alias no
     menciona FOLIO, y la columna del folio se resuelve aparte
     (`getColIdx('FOLIO') > -1 ? getColIdx('FOLIO') : getColIdx('ID')`, línea
     1133). La entrada de más es una divergencia, no una paridad.
  2. Por esa entrada, `get_col_idx("ID")` devuelve el índice de FOLIO siempre que
     la matriz destino no traiga una columna `ID` propia. Le pasa a toda hoja que
     se estrena —`_matriz_de_trabajo` la arranca con `ENCABEZADOS_TAREA`, que no
     tiene `ID`—, que es justo el caso de una actividad asignada a alguien que
     todavía no tiene fila en su tracker.
  3. `apply_batch_update` copia la fila celda por celda; `ID` viaja después de
     `FOLIO`, así que el UUID **pisa** el folio bueno.
  4. La fila se guarda con `dedupe_key = "<hoja>::<uuid>"`, distinta de la del
     original, así que el upsert no fusiona: nace una segunda fila.
  5. Como es una fila nueva, llega con su avance de origen. Por eso «volvieron a
     aparecer» las que ya estaban cerradas: lo cerrado fue la otra copia.

Lo que se fija aquí:

  * `ID` deja de ser alias de la **columna** FOLIO, como en `CODIGO.js`.
  * La clave primaria de Postgres no viaja en el payload de escritura
    (`limpiar_claves_tecnicas`), que es lo que `TaskWrite` ya declara con su
    `extra="forbid"`: «si el frontend manda `id` o `dedupe_key` … la petición
    falla … en vez de dejar que el cliente reescriba la identidad de la fila».

Lo que **no** se toca: el `ID` de las hojas de Apps Script, donde sí es el folio
(`A-1699...`, `PPC-123`). Solo se descarta el que tiene forma de UUID.
"""

from __future__ import annotations

from typing import Any, Dict, List

import pytest

from api.services import sheets, tracker_store
from api.services import tracker_rules as rules
from backend.core.engines.memoria import MemoryEngine
from backend.services.persistencia import PersistenciaTracker

# El UUID real de la captura, con su forma completa.
UUID_DE_POSTGRES = "b90ed1a7-7c3f-4d21-9a55-1f0c2e4b8a77"
FOLIO = "RC-0170"
CONCEPTO = "PROYECTO 3459 REUBICACION DE PUERTA DANFOSS PTE PO"

QUIEN_ASIGNA = "ROCIO ABIGAIL CASTRO COVARRUBIAS"
QUIEN_RECIBE = "ANTONIA PINEDA LOPEZ"


# ======================================================================
# 1. Qué es una clave de Postgres y qué no
# ======================================================================

@pytest.mark.parametrize("valor", [
    UUID_DE_POSTGRES,
    UUID_DE_POSTGRES.upper(),
    "00000000-0000-0000-0000-000000000000",
])
def test_un_uuid_es_la_clave_de_postgres(valor: str) -> None:
    assert rules.es_clave_de_postgres(valor) is True


@pytest.mark.parametrize("valor", [
    FOLIO, "PPC-544684601", "AV-3250", "A-1755123456789", "1772639658256",
    "ANTONIA PINEDA LOPEZ::ROW1604", "", None,
])
def test_un_folio_no_es_la_clave_de_postgres(valor: Any) -> None:
    """Incluidos los folios sintéticos y los de tipo timestamp de la migración."""
    assert rules.es_clave_de_postgres(valor) is False


# ======================================================================
# 2. `ID` no es alias de la columna FOLIO (paridad con CODIGO.js:1133)
# ======================================================================

# Los encabezados con los que `_matriz_de_trabajo` estrena una partición vacía.
ENCABEZADOS_HOJA_NUEVA = list(tracker_store.ENCABEZADOS_TAREA)


def _resolver(encabezados: List[str]):
    return rules._build_col_resolver([rules.normalize_header(h) for h in encabezados])


def test_id_no_cae_en_la_columna_folio_de_una_hoja_que_se_estrena() -> None:
    """La prueba que fallaba antes del arreglo: devolvía el índice de FOLIO."""
    resolver = _resolver(ENCABEZADOS_HOJA_NUEVA)

    assert resolver("FOLIO") == 0
    assert resolver("ID") == -1, "la clave primaria no tiene columna en esta hoja"


def test_id_sigue_resolviendo_a_su_propia_columna_cuando_existe() -> None:
    """La lectura de la base sí rinde `ID`: ahí la columna es suya."""
    resolver = _resolver(ENCABEZADOS_HOJA_NUEVA + ["ID"])

    assert resolver("ID") == len(ENCABEZADOS_HOJA_NUEVA)
    assert resolver("FOLIO") == 0


def test_una_hoja_cuyo_folio_se_llama_id_sigue_encontrandolo() -> None:
    """
    Paridad con `CODIGO.js:1133`: sin columna FOLIO, la del folio es `ID`.

    Es la forma de las hojas de Apps Script, donde `ID` **es** el folio. El
    arreglo no puede quitársela.
    """
    matriz = [["ID", "CONCEPTO", "FECHA", "ESTATUS"],
              ["MG-0001", "CAMBIAR TABLERO", "10/07/26", "ASIGNADO"]]

    res = rules.apply_batch_update(matriz, [{"FOLIO": "MG-0001", "ESTATUS": "HECHO"}],
                                   "MIGUEL GALLARDO")

    assert res.appended == 0, "la fila existe: hay que actualizarla, no duplicarla"
    assert [f for f in res.values if f[0] == "MG-0001"][0][3] == "HECHO"


def test_la_tabla_de_ventas_tampoco_confunde_su_clave_con_el_folio() -> None:
    """
    `quotes.id` es igual de UUID y `_valores_de_cotizaciones` lo expone igual, así
    que una cotización repartida a un vendedor sin filas corría el mismo riesgo.
    """
    resolver = _resolver(tracker_store.ENCABEZADOS_VENTAS)

    assert resolver("FOLIO") == 0
    assert resolver("ID") == -1


def test_el_uuid_no_pisa_el_folio_al_dar_de_alta_en_una_hoja_nueva() -> None:
    """El paso 3 de la cadena, aislado."""
    fila = {"FOLIO": FOLIO, "CONCEPTO": CONCEPTO, "FECHA": "21/07/26",
            "RESPONSABLE": QUIEN_RECIBE, "ID": UUID_DE_POSTGRES}

    res = rules.apply_batch_update([list(ENCABEZADOS_HOJA_NUEVA)], [fila], QUIEN_RECIBE)

    assert res.data[0]["FOLIO"] == FOLIO


# ======================================================================
# 3. El payload de escritura no lleva la identidad de la fila
# ======================================================================

def test_la_limpieza_quita_la_clave_primaria_y_deja_lo_capturable() -> None:
    task = rules.limpiar_claves_tecnicas({
        "FOLIO": FOLIO, "CONCEPTO": CONCEPTO, "AVANCE": "100",
        "ID": UUID_DE_POSTGRES, "DEDUPE_KEY": f"{QUIEN_RECIBE}::{FOLIO}",
        "SOURCE_SHEET": QUIEN_RECIBE, "CREATED_AT": "2026-07-21T13:22:00Z",
        "FOLIO_SINTETICO": False, "ASSIGNEE_ID": UUID_DE_POSTGRES,
    })

    assert task == {"FOLIO": FOLIO, "CONCEPTO": CONCEPTO, "AVANCE": "100"}


def test_la_limpieza_conserva_el_id_de_las_hojas_de_apps_script() -> None:
    """Ahí `ID` es el folio, no una clave de Postgres."""
    task = rules.limpiar_claves_tecnicas({"ID": "A-1755123456789", "TITULO": "JUNTA"})

    assert task == {"ID": "A-1755123456789", "TITULO": "JUNTA"}


def test_la_limpieza_conserva_los_metadatos_del_frontend() -> None:
    """`_tempId` es el candado anti doble clic: quitarlo lo apagaría."""
    task = rules.limpiar_claves_tecnicas(
        {"CONCEPTO": CONCEPTO, "_tempId": "temp_1", "ID": UUID_DE_POSTGRES})

    assert task["_tempId"] == "temp_1"
    assert "ID" not in task


def test_la_limpieza_es_idempotente() -> None:
    """Se aplica dos veces en el mismo guardado (entrada y persistencia)."""
    una = rules.limpiar_claves_tecnicas({"FOLIO": FOLIO, "ID": UUID_DE_POSTGRES})

    assert rules.limpiar_claves_tecnicas(dict(una)) == una == {"FOLIO": FOLIO}


def test_la_limpieza_muta_la_fila_que_recibe() -> None:
    """
    `_persist_batch` la aplica sobre las mismas filas que luego lee
    `save_tracker_batch` para el reverse sync: copiarlas les quitaría el folio
    que `apply_batch_update` acaba de asignar.
    """
    task = {"FOLIO": FOLIO, "ID": UUID_DE_POSTGRES}

    assert rules.limpiar_claves_tecnicas(task) is task
    assert "ID" not in task


# ======================================================================
# 4. El incidente completo, contra la base
# ======================================================================

@pytest.fixture
def motor() -> MemoryEngine:
    """La actividad existe en la tabla de quien la asignó, y en ninguna más."""
    return MemoryEngine({
        "tasks": [{
            "id": UUID_DE_POSTGRES,
            "dedupe_key": f"{QUIEN_ASIGNA}::{FOLIO}",
            "folio": FOLIO,
            "folio_sintetico": False,
            "source_sheet": QUIEN_ASIGNA,
            "assignee_raw": QUIEN_RECIBE,
            "concepto": CONCEPTO,
            "avance": 0.0,
            "status": "ASIGNADO",
            "fecha_alta": "2026-07-21",
            "hora_alta": "13:22",
            "prioridad": "ALTA",
            "riesgos": "ALTO",
            "fecha_estimada_fin": "2026-08-04",
            "created_at": "2026-07-21T13:22:00Z",
        }],
        "quotes": [], "people": [], "plan_semanal": [],
        "task_involucrados": [], "system_log": [], "profiles": [],
    })


@pytest.fixture
def tracker(monkeypatch: pytest.MonkeyPatch, motor: MemoryEngine) -> MemoryEngine:
    """
    El puente y la lectura, cableados al motor en memoria.

    La lectura pasa por `sheets._valores_de_tareas`, la misma que rinde la hoja
    en producción: es la que expone `ID` como columna y sin ella el reporte no se
    reproduce.
    """
    monkeypatch.setattr(tracker_store, "_persistencia",
                        lambda: PersistenciaTracker(motor))

    def leer(hoja: str) -> List[List[Any]]:
        filas = [f for f in motor.select("tasks")
                 if rules.normalize_staff_name(f.get("source_sheet"))
                 == rules.normalize_staff_name(hoja)]
        return sheets._valores_de_tareas(filas) or []

    monkeypatch.setattr(tracker_store, "read_values", leer)
    return motor


def _fila_como_la_rinde_la_api(motor: MemoryEngine, hoja: str) -> Dict[str, Any]:
    """La fila tal como la recibe —y la devuelve— el frontend, con su `ID`."""
    filas = [f for f in motor.select("tasks")
             if rules.normalize_staff_name(f.get("source_sheet"))
             == rules.normalize_staff_name(hoja)]
    valores = sheets._valores_de_tareas(filas)
    return dict(zip(valores[0], valores[1]))


def _folios_de(motor: MemoryEngine, hoja: str) -> List[str]:
    return sorted(str(f["folio"]) for f in motor.select("tasks")
                  if rules.normalize_staff_name(f.get("source_sheet"))
                  == rules.normalize_staff_name(hoja))


def test_la_fila_que_rinde_la_api_trae_la_clave_primaria(tracker: MemoryEngine) -> None:
    """El insumo del defecto: sin este `ID` en la fila no habría nada que arreglar."""
    fila = _fila_como_la_rinde_la_api(tracker, QUIEN_ASIGNA)

    assert fila["ID"] == UUID_DE_POSTGRES
    assert fila["FOLIO"] == FOLIO


def test_asi_se_duplicaba_la_actividad(tracker: MemoryEngine) -> None:
    """
    El reporte, reproducido: dos guardados dejaban dos filas en la misma tabla,
    una con el folio bueno y otra con el UUID.

    Antes del arreglo esto daba
    `['RC-0170', 'b90ed1a7-7c3f-4d21-9a55-1f0c2e4b8a77']`.
    """
    fila = _fila_como_la_rinde_la_api(tracker, QUIEN_ASIGNA)

    for _ in range(2):
        respuesta = tracker_store.save_tracker_batch(
            QUIEN_ASIGNA, [dict(fila)], username="ROCIO_CASTRO")
        assert respuesta["success"] is True, respuesta.get("message")

    assert _folios_de(tracker, QUIEN_RECIBE) == [FOLIO], (
        "la copia asignada es una sola fila, con el folio de la actividad")


def test_la_copia_asignada_conserva_el_folio_de_quien_la_creo(tracker: MemoryEngine) -> None:
    tracker_store.save_tracker_batch(
        QUIEN_ASIGNA, [_fila_como_la_rinde_la_api(tracker, QUIEN_ASIGNA)],
        username="ROCIO_CASTRO")

    copia = next(f for f in tracker.select("tasks")
                 if rules.normalize_staff_name(f["source_sheet"])
                 == rules.normalize_staff_name(QUIEN_RECIBE))
    assert copia["folio"] == FOLIO
    assert copia["dedupe_key"] == f"{QUIEN_RECIBE}::{FOLIO}"


def test_lo_que_ya_estaba_cerrado_no_reaparece_abierto(tracker: MemoryEngine) -> None:
    """
    La segunda mitad del reporte: «ya las había cerrado pero volvieron a
    aparecer». Volvían porque la fila nueva nacía con el avance del original.
    """
    tracker_store.save_tracker_batch(
        QUIEN_ASIGNA, [_fila_como_la_rinde_la_api(tracker, QUIEN_ASIGNA)],
        username="ROCIO_CASTRO")

    # Quien la recibió la cierra desde su propia tabla.
    suya = _fila_como_la_rinde_la_api(tracker, QUIEN_RECIBE)
    suya["AVANCE %"] = "100"
    suya["STATUS"] = "HECHO"
    respuesta = tracker_store.save_tracker_batch(
        QUIEN_RECIBE, [suya], username="ANTONIA_PINEDA")
    assert respuesta["success"] is True, respuesta.get("message")

    # Y quien la asignó vuelve a guardar su tabla ("Guardar Todo").
    tracker_store.save_tracker_batch(
        QUIEN_ASIGNA, [_fila_como_la_rinde_la_api(tracker, QUIEN_ASIGNA)],
        username="ROCIO_CASTRO")

    suyas = [f for f in tracker.select("tasks")
             if rules.normalize_staff_name(f["source_sheet"])
             == rules.normalize_staff_name(QUIEN_RECIBE)]
    assert len(suyas) == 1, "cerrar no puede dejar una segunda fila abierta"
    assert suyas[0]["avance"] == 100.0


def test_el_guardado_normal_sigue_asignando_folio_a_lo_nuevo(tracker: MemoryEngine) -> None:
    """El arreglo no puede dejar sin folio a una actividad que nace."""
    nueva = {"FOLIO": "", "ID": "", "CONCEPTO": "REVISION DE CORREOS",
             "FECHA": "21/07/26", "INVOLUCRADOS": QUIEN_ASIGNA,
             "PRIORIDADES": "ALTA", "RIESGOS": "ALTO",
             "FECHA_ESTIMADA_FIN": "04/08/26", "_tempId": "temp_9"}

    respuesta = tracker_store.save_tracker_batch(
        QUIEN_ASIGNA, [nueva], username="ROCIO_CASTRO")

    assert respuesta["success"] is True, respuesta.get("message")
    folios = _folios_de(tracker, QUIEN_ASIGNA)
    assert FOLIO in folios
    nuevos = [f for f in folios if f != FOLIO]
    assert len(nuevos) == 1 and nuevos[0].startswith("RA-"), folios
