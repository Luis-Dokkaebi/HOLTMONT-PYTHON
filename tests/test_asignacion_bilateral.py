"""
Asignación cruzada entre tablas y sincronización bilateral.

Las tres reglas que fija este archivo, dichas por el dueño:

1. Cualquiera puede asignar una actividad a otra persona desde su propio
   tracker. Al hacerlo, la actividad aparece **en las dos tablas**: la de quien
   asigna y la de quien recibe. Cuando quien la recibe la pone al 100 %, pasa a
   TAREAS REALIZADAS **en ambas**.
2. `ANTONIA_VENTAS` es la excepción: solo Toñita escribe ahí, y una actividad
   asignada "a Antonia" cae en su tracker personal
   (`ANTONIA PINEDA LOPEZ`), que es otra tabla.
3. La papa caliente **no** es lo mismo. Delega microtareas de una cotización, y
   el 100 % de una microtarea NO archiva la cotización: solo pinta su fase de
   verde, y la fase únicamente se pone verde cuando **todos** sus asignados
   terminan. Hasta entonces no se puede delegar la siguiente.

La regla 3 invierte la decisión anterior del proyecto, que sí archivaba la
maestra con el 100 % de un solo trabajador. Las pruebas que fijaban aquello
(`test_reverse_sync_sends_cierre_status`,
`test_la_venta_maestra_se_archiva_por_avance_del_trabajador`) se actualizaron a
la regla nueva, no se borraron: el comentario de `REVERSE_SYNC_BLOCKED_KEYS` ya
anticipaba este cambio y decía exactamente qué tocar.
"""

import os
import sys

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from api.services import asignacion  # noqa: E402
from api.services import tracker_rules as rules  # noqa: E402
from backend.services.identity import compute_dedupe_key  # noqa: E402

ENCABEZADOS = ["FOLIO", "CONCEPTO", "RESPONSABLE", "INVOLUCRADOS",
               "AVANCE", "ESTATUS", "FECHA"]


def _matriz(*filas):
    return [list(ENCABEZADOS)] + [list(f) for f in filas]


def _fila(folio="", concepto="", responsable="", involucrados="",
          avance="", estatus="", fecha="01/03/26"):
    return [folio, concepto, responsable, involucrados, avance, estatus, fecha]


def _log(*entradas):
    """PROCESO_LOG con la forma que escribe `upsert_proceso_log_entry`."""
    return [{"step": paso, "assignee": quien, "status": estado}
            for paso, quien, estado in entradas]


# ======================================================================
# 1. La clave de identidad: por qué las copias se colapsaban
# ======================================================================

def test_un_folio_global_da_la_misma_clave_en_todas_las_hojas():
    """
    El bloqueo de raíz, documentado como prueba.

    `AV-3250` lleva un prefijo de secuencia global, así que `compute_dedupe_key`
    devuelve el folio a secas **sin la hoja**. Dos copias en dos tablas
    distintas comparten clave, el upsert las colapsa en una sola fila y
    `_completar_obligatorias` fija el `source_sheet` del primero que escribió.
    Resultado: la delegación nunca llegaba a la tabla del trabajador.
    """
    assert compute_dedupe_key("AV-3250", "MIGUEL GALLARDO") == "AV-3250"
    assert compute_dedupe_key("AV-3250", "GERALDINE") == "AV-3250"


def test_la_copia_asignada_recibe_una_clave_propia_por_hoja():
    """La copia se identifica por hoja + folio, que es lo que la hace existir."""
    miguel = asignacion.clave_de_copia("AV-3250", "MIGUEL GALLARDO")
    geraldine = asignacion.clave_de_copia("AV-3250", "GERALDINE")

    assert miguel != geraldine
    assert miguel == "MIGUEL GALLARDO::AV-3250"


def test_la_clave_de_copia_coincide_con_la_normal_en_folios_de_persona():
    """
    Para un folio con iniciales no hay nada que arreglar: `compute_dedupe_key`
    ya lo alcanza por hoja. La función nueva no puede devolver algo distinto o
    estaría inventando una segunda fila para tareas que ya funcionan.
    """
    assert (asignacion.clave_de_copia("AS-0001", "GERALDINE")
            == compute_dedupe_key("AS-0001", "GERALDINE"))


@pytest.mark.parametrize("folio", ["", None, "   "])
def test_sin_folio_no_hay_clave_de_copia(folio):
    assert asignacion.clave_de_copia(folio, "GERALDINE") is None


# ======================================================================
# 2. A quién le aparece la actividad
# ======================================================================

def test_asignar_a_otra_persona_produce_una_copia_en_su_tabla():
    """El caso del dueño: Antonio le asigna a Geraldine desde su tracker."""
    destinos = asignacion.destinos_espejo(
        "ANTONIO SALAZAR", {"FOLIO": "AS-0001", "RESPONSABLE": "GERALDINE"})

    assert destinos == ["GERALDINE"]


def test_asignarse_a_uno_mismo_no_duplica_la_fila():
    """Antonio como responsable de su propia tarea no genera copia."""
    destinos = asignacion.destinos_espejo(
        "ANTONIO SALAZAR", {"FOLIO": "AS-0001", "RESPONSABLE": "ANTONIO SALAZAR"})

    assert destinos == []


def test_varios_responsables_reciben_una_copia_cada_uno():
    """
    Supuesto asumido (el dueño no eligió): con varios nombres en RESPONSABLE,
    cada quien recibe la actividad en su tabla.
    """
    destinos = asignacion.destinos_espejo(
        "ANTONIO SALAZAR",
        {"FOLIO": "AS-0001", "RESPONSABLE": "GERALDINE, MIGUEL GALLARDO"})

    assert destinos == ["GERALDINE", "MIGUEL GALLARDO"]


def test_asignar_a_antonia_cae_en_su_tracker_personal_no_en_ventas():
    """
    "Las tareas que se asignen a ANTONIA PINEDA caen en su tabla TRACKER, son
    dos tablas diferentes." La tabla de ventas no recibe asignaciones de nadie.
    """
    destinos = asignacion.destinos_espejo(
        "ANTONIO SALAZAR", {"FOLIO": "AS-0001", "RESPONSABLE": "ANTONIA VENTAS"})

    assert destinos == [rules.ANTONIA_PERSONAL_SHEET]


def test_ninguna_asignacion_puede_escribir_en_la_tabla_de_ventas():
    """La Ley de Antonia aplicada al espejo: ANTONIA_VENTAS nunca es destino."""
    destinos = asignacion.destinos_espejo(
        "MIGUEL GALLARDO",
        {"FOLIO": "MG-0001", "RESPONSABLE": "ANTONIA_VENTAS, GERALDINE"})

    assert rules.SALES_MASTER_SHEET not in destinos
    assert destinos == [rules.ANTONIA_PERSONAL_SHEET, "GERALDINE"]


def test_el_sufijo_de_ventas_no_estrena_una_hoja_aparte():
    """"GERALDINE (VENTAS)" es la misma persona que "GERALDINE"."""
    destinos = asignacion.destinos_espejo(
        "ANTONIO SALAZAR", {"FOLIO": "AS-0001", "RESPONSABLE": "GERALDINE (VENTAS)"})

    assert destinos == ["GERALDINE"]


# ======================================================================
# 3. Qué lleva la copia
# ======================================================================

def test_la_copia_conserva_folio_concepto_y_avance():
    """Es la misma actividad, no una nueva: comparte folio y estado."""
    espejo = asignacion.construir_espejo(
        "ANTONIO SALAZAR",
        {"FOLIO": "AS-0001", "CONCEPTO": "Revisar planos", "AVANCE": "40",
         "ESTATUS": "EN PROCESO", "RESPONSABLE": "GERALDINE"},
        "GERALDINE", username="ANTONIO_SALAZAR")

    assert espejo["FOLIO"] == "AS-0001"
    assert espejo["CONCEPTO"] == "Revisar planos"
    assert espejo["AVANCE"] == "40"
    assert espejo["RESPONSABLE"] == "GERALDINE"


def test_la_copia_no_arrastra_metadatos_del_frontend():
    """
    `_tempId` es del evento de UI que la creó en la tabla de Antonio. Copiarlo
    haría que el gatekeeper tomara la copia de Geraldine por la misma alta y la
    descartara.
    """
    espejo = asignacion.construir_espejo(
        "ANTONIO SALAZAR",
        {"FOLIO": "AS-0001", "CONCEPTO": "Revisar planos", "RESPONSABLE": "GERALDINE",
         "_tempId": "temp_123", "_rowIndex": 7},
        "GERALDINE")

    assert not any(str(k).startswith("_") for k in espejo)


def test_la_copia_deja_rastro_de_quien_asigno():
    espejo = asignacion.construir_espejo(
        "ANTONIO SALAZAR",
        {"FOLIO": "AS-0001", "CONCEPTO": "Revisar planos", "RESPONSABLE": "GERALDINE"},
        "GERALDINE", username="ANTONIO_SALAZAR")

    assert "ANTONIO SALAZAR" in espejo["COMENTARIOS"].upper()


# ======================================================================
# 4. Sincronización bilateral
# ======================================================================

def test_el_100_de_geraldine_viaja_a_la_tabla_de_antonio():
    """El corazón de la bilateralidad: lo que archiva, se propaga."""
    cambios = asignacion.campos_sincronizables(
        {"FOLIO": "AS-0001", "AVANCE": "100", "ESTATUS": "HECHO",
         "CONCEPTO": "Revisar planos [editado por Geraldine]"})

    assert cambios["AVANCE"] == "100"
    assert cambios["ESTATUS"] == "HECHO"


def test_la_sincronizacion_no_pisa_el_concepto_ni_el_responsable():
    """
    Solo viaja el estado. Si viajara el CONCEPTO, Geraldine reescribiría el
    texto de la actividad en la tabla de Antonio; si viajara RESPONSABLE, la
    copia de Antonio se reasignaría a sí misma.
    """
    cambios = asignacion.campos_sincronizables(
        {"FOLIO": "AS-0001", "AVANCE": "100", "CONCEPTO": "otra cosa",
         "RESPONSABLE": "GERALDINE"})

    assert "CONCEPTO" not in cambios
    assert "RESPONSABLE" not in cambios


def test_la_sincronizacion_lleva_el_folio_para_encontrar_la_fila():
    cambios = asignacion.campos_sincronizables({"FOLIO": "AS-0001", "AVANCE": "100"})

    assert cambios["FOLIO"] == "AS-0001"


def test_sin_cambios_de_estado_no_se_sincroniza_nada():
    """Editar solo el concepto no dispara escrituras en la otra tabla."""
    assert asignacion.campos_sincronizables(
        {"FOLIO": "AS-0001", "CONCEPTO": "Revisar planos"}) is None


# ======================================================================
# 5. Papa caliente: la fase se pone verde con TODOS al 100 %
# ======================================================================

def test_una_fase_con_dos_asignados_no_se_cierra_con_uno_solo():
    log = _log(("CD", "MIGUEL GALLARDO", "DONE"),
               ("CD", "ROLANDO MORENO", "IN_PROGRESS"))

    assert asignacion.fase_completa(log, "CD") is False


def test_la_fase_se_cierra_cuando_todos_terminan():
    log = _log(("CD", "MIGUEL GALLARDO", "DONE"),
               ("CD", "ROLANDO MORENO", "DONE"))

    assert asignacion.fase_completa(log, "CD") is True


def test_una_fase_sin_delegar_no_cuenta_como_completa():
    assert asignacion.fase_completa(_log(("CD", "MIGUEL", "DONE")), "EP") is False


def test_no_se_delega_la_siguiente_fase_con_la_actual_abierta():
    """
    "Hasta que todos tengan 100% ... podrá pasar a la siguiente delegación."
    Supuesto asumido (el dueño no eligió): el bloqueo es duro.
    """
    log = _log(("CD", "MIGUEL GALLARDO", "DONE"),
               ("CD", "ROLANDO MORENO", "IN_PROGRESS"))

    assert asignacion.puede_delegar(log, "EP") is False


def test_se_delega_la_siguiente_cuando_la_actual_esta_verde():
    log = _log(("CD", "MIGUEL GALLARDO", "DONE"),
               ("CD", "ROLANDO MORENO", "DONE"))

    assert asignacion.puede_delegar(log, "EP") is True


def test_siempre_se_puede_sumar_gente_a_la_fase_en_curso():
    """Añadir un tercer involucrado a CD no es "pasar a la siguiente"."""
    log = _log(("CD", "MIGUEL GALLARDO", "IN_PROGRESS"))

    assert asignacion.puede_delegar(log, "CD") is True


def test_la_primera_delegacion_no_esta_bloqueada():
    assert asignacion.puede_delegar([], "L") is True


def test_papa_caliente_rechaza_saltarse_una_fase_abierta():
    """La regla llega hasta `apply_hot_potato`, no se queda en el helper."""
    tarea = {"FOLIO": "AV-3250", "CONCEPTO": "Cotizar nave",
             "INVOLUCRADOS": "GERALDINE", "_assignStep": "EP",
             "PROCESO_LOG": rules.json.dumps(
                 _log(("CD", "MIGUEL GALLARDO", "IN_PROGRESS")))}

    with pytest.raises(rules.FaseEnCurso):
        rules.apply_hot_potato(rules.SALES_MASTER_SHEET, tarea, {}, "ANTONIA_VENTAS")


# ======================================================================
# 6. Papa caliente: el 100 % de una microtarea NO archiva la cotización
# ======================================================================

def test_el_100_de_una_microtarea_no_cierra_la_cotizacion_maestra():
    """
    La regla nueva. Antes AVANCE y ESTATUS viajaban y el auto-archivado se
    llevaba la venta entera a TAREAS REALIZADAS con que un solo trabajador
    cerrara su fase.
    """
    payload = rules.build_reverse_sync_payload(
        "MIGUEL GALLARDO",
        {"FOLIO": "AV-3250", "AVANCE": "100", "ESTATUS": "HECHO"},
        {"CONCEPTO": "Cotizar nave [Calculo y Diseño]", "AVANCE": "100"},
        {"PROCESO_LOG": "[]"})

    assert payload is not None
    assert "AVANCE" not in payload, "el avance de la microtarea no es el de la venta"
    assert "ESTATUS" not in payload


def test_pero_la_fase_si_se_pinta_de_verde():
    """Lo que sí viaja: el estado del proceso, que es lo que ve Toñita."""
    payload = rules.build_reverse_sync_payload(
        "MIGUEL GALLARDO",
        {"FOLIO": "AV-3250", "AVANCE": "100"},
        {"CONCEPTO": "Cotizar nave [Calculo y Diseño]", "AVANCE": "100"},
        {"PROCESO_LOG": "[]"})

    assert '"status": "DONE"' in payload["PROCESO_LOG"]
    assert "🟢 CD" in payload["MAP COT"]


def test_la_fase_sigue_roja_mientras_falte_un_asignado():
    """Dos delegados, uno cierra: la fase no se pone verde todavía."""
    log = rules.json.dumps(_log(("CD", "MIGUEL GALLARDO", "IN_PROGRESS"),
                                ("CD", "ROLANDO MORENO", "IN_PROGRESS")))
    payload = rules.build_reverse_sync_payload(
        "MIGUEL GALLARDO",
        {"FOLIO": "AV-3250", "AVANCE": "100", "RESPONSABLE": "MIGUEL GALLARDO"},
        {"CONCEPTO": "Cotizar nave [Calculo y Diseño]", "AVANCE": "100"},
        {"PROCESO_LOG": log})

    assert "🔴 CD" in payload["MAP COT"], "falta ROLANDO MORENO"


def test_una_tarea_normal_si_sincroniza_avance_y_estatus():
    """
    El otro lado de la misma moneda: sin marca de fase no es papa caliente, es
    una asignación normal, y ahí el 100 % **sí** debe viajar para archivar en
    las dos tablas.
    """
    payload = rules.build_reverse_sync_payload(
        "GERALDINE",
        {"FOLIO": "AV-3250", "AVANCE": "100", "ESTATUS": "HECHO"},
        {"CONCEPTO": "Cotizar nave", "AVANCE": "100"},
        {"PROCESO_LOG": "[]"})

    assert payload["AVANCE"] == "100"
    assert payload["ESTATUS"] == "HECHO"


# ======================================================================
# 7. Integración: el guardado real escribe en las dos tablas
# ======================================================================

class _EngineDeCopias:
    """
    Motor mínimo: dice en qué hojas vive cada folio, que es el vínculo real.

    Cada copia se declara como nombre de hoja a secas o como diccionario con lo
    que la prueba necesite (`assignee_raw`, `concepto`, `created_at`). Las dos
    formas conviven para que las pruebas que solo miran hojas no tengan que
    escribir un diccionario completo.
    """

    def __init__(self, por_folio):
        self.por_folio = por_folio
        self.borrados = []

    @staticmethod
    def _fila(entrada, orden):
        if isinstance(entrada, dict):
            fila = dict(entrada)
            fila.setdefault("created_at", f"2026-01-{orden + 1:02d}T00:00:00Z")
            return fila
        return {"source_sheet": entrada,
                "created_at": f"2026-01-{orden + 1:02d}T00:00:00Z"}

    def select(self, tabla, columnas=None, donde=None, **kwargs):
        folio = (donde or {}).get("folio")
        return [self._fila(e, i) for i, e in enumerate(self.por_folio.get(folio, []))]

    def borrar(self, tabla, donde):
        self.borrados.append({"tabla": tabla, "donde": dict(donde)})


class _PersistenciaFalsa:
    def __init__(self, por_folio):
        self.engine = _EngineDeCopias(por_folio)


@pytest.fixture()
def copias_en_la_base():
    """
    Folio -> copias ya existentes. Lo llena cada prueba.

    La primera de la lista es la más antigua, es decir, la hoja **originadora**:
    es el orden que usa `_hoja_originadora` para saber quién puede reasignar.
    """
    return {}


@pytest.fixture()
def escrituras(monkeypatch, copias_en_la_base):
    """Intercepta `_persist_batch` y devuelve la lista de (hoja, tareas)."""
    from api.services import tracker_store

    registro = []

    def _falso_persist(sheet_name, tasks, skip_notify=False, username="",
                       persistencia=None, como_copia=False):
        registro.append({"hoja": sheet_name, "tareas": [dict(t) for t in tasks],
                         "como_copia": como_copia})
        return rules.BatchResult(_matriz(), [dict(t) for t in tasks], False, 0, [])

    monkeypatch.setattr(tracker_store, "_persist_batch", _falso_persist)
    monkeypatch.setattr(tracker_store, "_persistencia",
                        lambda: _PersistenciaFalsa(copias_en_la_base))
    monkeypatch.setattr(tracker_store, "find_row_object", lambda hoja, folio: {})
    return registro


def test_al_asignar_la_actividad_se_escribe_en_las_dos_tablas(escrituras):
    """
    El requisito textual: "al asignarla como responsable le debe aparecer en su
    tabla a Geraldine y a él".
    """
    from api.services import tracker_store

    tracker_store.save_tracker_batch(
        "ANTONIO SALAZAR",
        [{"FOLIO": "AS-0001", "CONCEPTO": "Revisar planos", "RESPONSABLE": "GERALDINE"}],
        "ANTONIO_SALAZAR")

    hojas = [e["hoja"] for e in escrituras]
    assert "ANTONIO SALAZAR" in hojas
    assert "GERALDINE" in hojas


def test_el_100_de_geraldine_archiva_en_las_dos_tablas(escrituras, copias_en_la_base):
    """
    Sincronización bilateral de vuelta: Geraldine cierra, Antonio se entera.

    La copia se encuentra por folio en la base, que es el vínculo entre las dos
    filas. No hace falta que el frontend recuerde quién asignó.
    """
    from api.services import tracker_store

    # Las copias se declaran con su CONCEPTO, que es como están en la base: dos
    # copias de una actividad asignada lo comparten, y por eso la
    # sincronización las alcanza. Ver `tests/test_actividades_que_regresan.py`.
    copias_en_la_base["AS-0001"] = [
        {"source_sheet": "GERALDINE", "concepto": "Revisar planos"},
        {"source_sheet": "ANTONIO SALAZAR", "concepto": "Revisar planos"},
    ]

    tracker_store.save_tracker_batch(
        "GERALDINE",
        [{"FOLIO": "AS-0001", "CONCEPTO": "Revisar planos",
          "RESPONSABLE": "GERALDINE", "AVANCE": "100", "ESTATUS": "HECHO"}],
        "GERALDINE")

    hacia_antonio = [e for e in escrituras if e["hoja"] == "ANTONIO SALAZAR"]
    assert hacia_antonio, "la tabla de quien asignó también se cierra"
    assert hacia_antonio[0]["tareas"][0]["AVANCE"] == "100"
    assert hacia_antonio[0]["tareas"][0]["ESTATUS"] == "HECHO"


def test_la_sincronizacion_no_reescribe_la_tabla_de_quien_cierra(escrituras, copias_en_la_base):
    """Geraldine ya se guardó en su propio `_persist_batch`: no se duplica."""
    from api.services import tracker_store

    copias_en_la_base["AS-0001"] = ["GERALDINE", "ANTONIO SALAZAR"]

    tracker_store.save_tracker_batch(
        "GERALDINE",
        [{"FOLIO": "AS-0001", "CONCEPTO": "Revisar planos",
          "RESPONSABLE": "GERALDINE", "AVANCE": "100"}],
        "GERALDINE")

    assert [e["hoja"] for e in escrituras].count("GERALDINE") == 1


def test_guardar_sin_responsable_no_escribe_en_ninguna_otra_tabla(escrituras):
    from api.services import tracker_store

    tracker_store.save_tracker_batch(
        "ANTONIO SALAZAR",
        [{"FOLIO": "AS-0001", "CONCEPTO": "Revisar planos"}],
        "ANTONIO_SALAZAR")

    assert [e["hoja"] for e in escrituras] == ["ANTONIO SALAZAR"]


def test_editar_solo_el_concepto_no_toca_la_tabla_de_nadie(escrituras, copias_en_la_base):
    """Sin cambio de estado no hay sincronización: evita escrituras por cada tecleo."""
    from api.services import tracker_store

    copias_en_la_base["AS-0001"] = ["GERALDINE", "ANTONIO SALAZAR"]

    tracker_store.save_tracker_batch(
        "GERALDINE",
        [{"FOLIO": "AS-0001", "CONCEPTO": "Revisar planos v2",
          "RESPONSABLE": "GERALDINE"}],
        "GERALDINE")

    assert [e["hoja"] for e in escrituras] == ["GERALDINE"]


def test_nadie_mas_que_antonia_captura_en_la_tabla_de_ventas(escrituras):
    """
    La Ley de Antonia aplicada al espejo, que es una vía de escritura nueva.

    Lo que se prohíbe es **capturar/asignar** en la tabla de ventas: el guardado
    de Miguel se redirige al tracker personal de Toñita y ningún espejo apunta a
    `ANTONIA_VENTAS`. El reverse sync que sí la escribe es otro canal —progreso
    de un folio `AV-` que vuelve a su maestra— y ese es el comportamiento que se
    quiere: es como Toñita ve avanzar sus cotizaciones.
    """
    from api.services import tracker_store

    tracker_store.save_tracker_batch(
        rules.SALES_MASTER_SHEET,
        [{"FOLIO": "AV-3250", "CONCEPTO": "Cotizar nave", "RESPONSABLE": "GERALDINE"}],
        "MIGUEL_GALLARDO")

    assert escrituras[0]["hoja"] == rules.ANTONIA_PERSONAL_SHEET, (
        "la captura se redirige fuera de la tabla de ventas")
    espejos = [e["hoja"] for e in escrituras[1:] if e["hoja"] == rules.SALES_MASTER_SHEET
               and "AVANCE" in e["tareas"][0]]
    assert not espejos, "ninguna asignación aterriza en la tabla de ventas"


# ======================================================================
# 8. La copia ocupa su propia fila en la base
# ======================================================================
#
# Es la mitad que no se ve desde las reglas: aunque `save_tracker_batch` mande
# la copia a la hoja correcta, si la clave de identidad es la misma el upsert
# la colapsa contra la fila original y la delegación no aparece por ningún lado.

from backend.core.engines.memoria import MemoryEngine  # noqa: E402
from backend.core.config import Settings  # noqa: E402
from backend.repositories.tasks import TaskRepository  # noqa: E402
from backend.schemas.task import TaskWrite  # noqa: E402


def _repo(filas=()):
    engine = MemoryEngine({"tasks": [dict(f) for f in filas], "people": []})
    return TaskRepository(engine, settings=Settings(
        database_url=None, supabase_url=None, supabase_key=None,
        motor_forzado="memoria", escritura_habilitada=True))


MAESTRA_AV = {
    "id": "11111111-1111-1111-1111-111111111111",
    "dedupe_key": "AV-3250",
    "folio": "AV-3250",
    "source_sheet": "ANTONIA_VENTAS",
    "concepto": "COTIZAR NAVE",
    "avance": 40.0,
    "status": "EN PROCESO",
}


def test_la_copia_de_un_folio_global_no_pisa_la_fila_original():
    """
    El fallo de raíz, extremo a extremo.

    Antes: la copia para GERALDINE se guardaba con clave `"AV-3250"`, el upsert
    encontraba la fila de ANTONIA_VENTAS y la actualizaba. Resultado: una sola
    fila, y la delegación no aparecía en la tabla de nadie.
    """
    repo = _repo([MAESTRA_AV])

    repo.guardar_lote("GERALDINE", [TaskWrite.desde_hoja(
        {"FOLIO": "AV-3250", "CONCEPTO": "COTIZAR NAVE", "AVANCE": "0"})],
        como_copia=True)

    filas = repo.engine.select("tasks")
    assert len(filas) == 2, "la copia es una fila nueva, no una sobrescritura"
    hojas = {f["source_sheet"] for f in filas}
    assert hojas == {"ANTONIA_VENTAS", "GERALDINE"}


def test_la_fila_original_conserva_su_avance():
    """Guardar la copia no puede mover el avance de la maestra."""
    repo = _repo([MAESTRA_AV])

    repo.guardar_lote("GERALDINE", [TaskWrite.desde_hoja(
        {"FOLIO": "AV-3250", "CONCEPTO": "COTIZAR NAVE", "AVANCE": "100"})],
        como_copia=True)

    maestra = next(f for f in repo.engine.select("tasks")
                   if f["source_sheet"] == "ANTONIA_VENTAS")
    assert maestra["avance"] == 40.0


def test_editar_la_copia_actualiza_la_copia_y_no_crea_otra():
    """Segunda edición desde la misma hoja: sigue siendo la misma fila."""
    repo = _repo([MAESTRA_AV])

    for avance in ("30", "60"):
        repo.invalidar_caches()
        repo.guardar_lote("GERALDINE", [TaskWrite.desde_hoja(
            {"FOLIO": "AV-3250", "CONCEPTO": "COTIZAR NAVE", "AVANCE": avance})],
            como_copia=True)

    filas = repo.engine.select("tasks")
    assert len(filas) == 2
    copia = next(f for f in filas if f["source_sheet"] == "GERALDINE")
    assert copia["avance"] == 60.0


def test_una_fila_global_ya_existente_conserva_su_clave_historica():
    """
    Las 4.626 filas de la migración no se tocan.

    Si la fila que se está guardando ya existe **en esa misma hoja** con la
    clave global, se sigue usando esa: cambiarle la identidad crearía un
    duplicado de cada tarea que hoy funciona.
    """
    repo = _repo([MAESTRA_AV])

    repo.guardar_lote("ANTONIA_VENTAS", [TaskWrite.desde_hoja(
        {"FOLIO": "AV-3250", "CONCEPTO": "COTIZAR NAVE", "AVANCE": "70"})],
        como_copia=True)

    filas = repo.engine.select("tasks")
    assert len(filas) == 1, "es la misma fila, no una nueva"
    assert filas[0]["dedupe_key"] == "AV-3250"
    assert filas[0]["avance"] == 70.0


def test_los_folios_de_persona_siguen_igual():
    """No hay cambio de identidad donde no hacía falta."""
    repo = _repo()

    repo.guardar_lote("GERALDINE", [TaskWrite.desde_hoja(
        {"FOLIO": "AS-0001", "CONCEPTO": "REVISAR PLANOS"})])

    assert repo.engine.select("tasks")[0]["dedupe_key"] == "GERALDINE::AS-0001"


def test_el_espejo_se_guarda_declarado_como_copia(escrituras):
    """
    Une las dos mitades: sin `como_copia=True` la fila de Geraldine compartiría
    `dedupe_key` con la de Antonio en cuanto el folio fuera de secuencia global,
    y el upsert la colapsaría.
    """
    from api.services import tracker_store

    tracker_store.save_tracker_batch(
        "ANTONIO SALAZAR",
        [{"FOLIO": "PPC-500", "CONCEPTO": "Revisar planos", "RESPONSABLE": "GERALDINE"}],
        "ANTONIO_SALAZAR")

    copia = next(e for e in escrituras if e["hoja"] == "GERALDINE")
    assert copia["como_copia"] is True
    original = next(e for e in escrituras if e["hoja"] == "ANTONIO SALAZAR")
    assert original["como_copia"] is False, "la fila propia no es una copia"


def test_cerrar_una_microtarea_no_toca_la_de_los_demas_delegados(escrituras, copias_en_la_base):
    """
    Dos trabajadores tienen la misma fase de `AV-3250`. Que Miguel cierre la
    suya no puede poner al 100 % la de Rolando: son microtareas distintas de la
    misma cotización, y el verde de la fase depende justo de que cada quien
    reporte lo suyo.

    Sin este filtro, la sincronización por folio —que es correcta para una
    actividad asignada— arrastraría al resto de los delegados.
    """
    from api.services import tracker_store

    copias_en_la_base["AV-3250"] = ["MIGUEL GALLARDO", "ROLANDO MORENO",
                                    rules.SALES_MASTER_SHEET]

    tracker_store.save_tracker_batch(
        "MIGUEL GALLARDO",
        [{"FOLIO": "AV-3250", "CONCEPTO": "Cotizar nave [Calculo y Diseño]",
          "AVANCE": "100", "ESTATUS": "HECHO"}],
        "MIGUEL_GALLARDO")

    assert "ROLANDO MORENO" not in [e["hoja"] for e in escrituras]


# ======================================================================
# 9. Reasignar: solo el originador, y la copia anterior se retira
# ======================================================================
#
# Las dos reglas que eligió el dueño para el caso de la reasignación:
#   * "Se retira de la tabla de Geraldine."
#   * "No: solo el originador reasigna."
#
# La hoja originadora es la más antigua de las que comparten folio. No hace
# falta columna nueva: `created_at` ya distingue el original de sus copias,
# porque la copia se escribe después.

def _copia(hoja, responsable="", concepto="Revisar planos"):
    return {"source_sheet": hoja, "assignee_raw": responsable, "concepto": concepto}


def test_reasignar_retira_la_copia_del_responsable_anterior(escrituras, copias_en_la_base):
    """Antonio cambia de Geraldine a Miguel: Geraldine deja de verla activa."""
    from api.services import tracker_store

    copias_en_la_base["AS-0001"] = [
        _copia("ANTONIO SALAZAR", "GERALDINE"),
        _copia("GERALDINE", "GERALDINE"),
    ]

    tracker_store.save_tracker_batch(
        "ANTONIO SALAZAR",
        [{"FOLIO": "AS-0001", "CONCEPTO": "Revisar planos", "RESPONSABLE": "MIGUEL GALLARDO"}],
        "ANTONIO_SALAZAR")

    hojas = [e["hoja"] for e in escrituras]
    assert "MIGUEL GALLARDO" in hojas, "el nuevo responsable la recibe"
    assert "GERALDINE" not in hojas, "a la anterior ya no se le escribe nada"


def test_la_copia_retirada_se_borra_por_su_clave_de_copia(monkeypatch, copias_en_la_base):
    """El borrado apunta a la fila de Geraldine, nunca a la de Antonio."""
    from api.services import tracker_store

    persistencia = _PersistenciaFalsa(copias_en_la_base)
    copias_en_la_base["AS-0001"] = [
        _copia("ANTONIO SALAZAR", "GERALDINE"),
        _copia("GERALDINE", "GERALDINE"),
    ]
    monkeypatch.setattr(tracker_store, "_persist_batch",
                        lambda *a, **k: rules.BatchResult(_matriz(), [dict(t) for t in a[1]], False, 0, []))
    monkeypatch.setattr(tracker_store, "_persistencia", lambda: persistencia)
    monkeypatch.setattr(tracker_store, "find_row_object", lambda hoja, folio: {})

    tracker_store.save_tracker_batch(
        "ANTONIO SALAZAR",
        [{"FOLIO": "AS-0001", "CONCEPTO": "Revisar planos", "RESPONSABLE": "MIGUEL GALLARDO"}],
        "ANTONIO_SALAZAR")

    claves = [b["donde"].get("dedupe_key") for b in persistencia.engine.borrados]
    assert "GERALDINE::AS-0001" in claves
    assert "ANTONIO SALAZAR::AS-0001" not in claves, "la fila original nunca se borra"


def test_no_se_retiran_las_microtareas_de_papa_caliente(monkeypatch, copias_en_la_base):
    """
    Las fases delegadas comparten folio con la cotización. Cambiar el
    responsable de la fila maestra no puede borrar el trabajo repartido.
    """
    from api.services import tracker_store

    persistencia = _PersistenciaFalsa(copias_en_la_base)
    copias_en_la_base["AV-3250"] = [
        _copia(rules.SALES_MASTER_SHEET, "GERALDINE", "Cotizar nave"),
        _copia("MIGUEL GALLARDO", "MIGUEL GALLARDO", "Cotizar nave [Calculo y Diseño]"),
    ]
    monkeypatch.setattr(tracker_store, "_persist_batch",
                        lambda *a, **k: rules.BatchResult(_matriz(), [dict(t) for t in a[1]], False, 0, []))
    monkeypatch.setattr(tracker_store, "_persistencia", lambda: persistencia)
    monkeypatch.setattr(tracker_store, "find_row_object", lambda hoja, folio: {})
    monkeypatch.setattr(rules, "apply_hot_potato", lambda *a, **k: None)

    tracker_store.save_tracker_batch(
        rules.SALES_MASTER_SHEET,
        [{"FOLIO": "AV-3250", "CONCEPTO": "Cotizar nave", "RESPONSABLE": "ROLANDO MORENO"}],
        "ANTONIA_VENTAS")

    claves = [b["donde"].get("dedupe_key") for b in persistencia.engine.borrados]
    assert "MIGUEL GALLARDO::AV-3250" not in claves


def test_geraldine_no_puede_reasignar_la_actividad(escrituras, copias_en_la_base):
    """
    Regla elegida: solo quien creó la actividad cambia el responsable.
    Geraldine puede avanzarla o cerrarla, no pasársela a otro.
    """
    from api.services import tracker_store

    copias_en_la_base["AS-0001"] = [
        _copia("ANTONIO SALAZAR", "GERALDINE"),
        _copia("GERALDINE", "GERALDINE"),
    ]

    res = tracker_store.save_tracker_batch(
        "GERALDINE",
        [{"FOLIO": "AS-0001", "CONCEPTO": "Revisar planos", "RESPONSABLE": "MIGUEL GALLARDO"}],
        "GERALDINE")

    assert res["success"] is False
    assert "ANTONIO SALAZAR" in res["message"], "dice a quién pedírselo"
    assert escrituras == [], "no se guarda nada del lote"


def test_geraldine_si_puede_avanzar_y_cerrar_su_actividad(escrituras, copias_en_la_base):
    """El otro lado: sin cambiar el responsable, trabaja con normalidad."""
    from api.services import tracker_store

    copias_en_la_base["AS-0001"] = [
        _copia("ANTONIO SALAZAR", "GERALDINE"),
        _copia("GERALDINE", "GERALDINE"),
    ]

    res = tracker_store.save_tracker_batch(
        "GERALDINE",
        [{"FOLIO": "AS-0001", "CONCEPTO": "Revisar planos",
          "RESPONSABLE": "GERALDINE", "AVANCE": "100"}],
        "GERALDINE")

    assert res["success"] is True
    assert "GERALDINE" in [e["hoja"] for e in escrituras]


def test_el_originador_si_puede_reasignar(escrituras, copias_en_la_base):
    from api.services import tracker_store

    copias_en_la_base["AS-0001"] = [
        _copia("ANTONIO SALAZAR", "GERALDINE"),
        _copia("GERALDINE", "GERALDINE"),
    ]

    res = tracker_store.save_tracker_batch(
        "ANTONIO SALAZAR",
        [{"FOLIO": "AS-0001", "CONCEPTO": "Revisar planos", "RESPONSABLE": "MIGUEL GALLARDO"}],
        "ANTONIO_SALAZAR")

    assert res["success"] is True


def test_una_actividad_nueva_no_esta_bloqueada(escrituras):
    """Sin copias previas no hay originador que proteger: se está creando."""
    from api.services import tracker_store

    res = tracker_store.save_tracker_batch(
        "GERALDINE",
        [{"FOLIO": "GE-0001", "CONCEPTO": "Nueva", "RESPONSABLE": "MIGUEL GALLARDO"}],
        "GERALDINE")

    assert res["success"] is True


def test_guardar_sin_tocar_el_responsable_no_dispara_el_bloqueo(escrituras, copias_en_la_base):
    """
    "Guardar todo" reenvía la tabla entera con su RESPONSABLE intacto. Si el
    bloqueo mirara solo la presencia de la columna, Geraldine no podría guardar
    nunca.
    """
    from api.services import tracker_store

    copias_en_la_base["AS-0001"] = [
        _copia("ANTONIO SALAZAR", "GERALDINE"),
        _copia("GERALDINE", "GERALDINE"),
    ]

    res = tracker_store.save_tracker_batch(
        "GERALDINE",
        [{"FOLIO": "AS-0001", "CONCEPTO": "Revisar planos", "RESPONSABLE": "GERALDINE"}],
        "GERALDINE")

    assert res["success"] is True
