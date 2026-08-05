"""
El flujo diario completo: asignar → tabla de la persona → 100% → archivado →
sincronización en las dos tablas.

Es la pregunta que hay que poder responder con una prueba y no de memoria:
"¿ya puedo asignar actividades, y cuando alguien las pone al 100% pasan a tareas
realizadas y se reflejan en las dos tablas?".

El caso que motivó este archivo es
`test_reverse_sync_desde_la_hoja_propia_del_trabajador`: la condición de reverse
sync era `"(VENTAS)" in hoja_destino`, y una tarea delegada por papa caliente cae
en la hoja **propia** del trabajador (`MIGUEL GALLARDO`), que no contiene
"(VENTAS)". Resultado: el trabajador la cerraba y la tabla maestra nunca se
enteraba. Los folios `AP-` no se sincronizaban en absoluto.
"""

import os
import sys

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from api.services import tracker_rules as rules  # noqa: E402

ENCABEZADOS = ["FOLIO", "CONCEPTO", "RESPONSABLE", "INVOLUCRADOS",
               "AVANCE", "ESTATUS", "FECHA"]


def _matriz(*filas):
    return [list(ENCABEZADOS)] + [list(f) for f in filas]


def _fila(folio="", concepto="", responsable="", involucrados="",
          avance="", estatus="", fecha="01/03/26"):
    return [folio, concepto, responsable, involucrados, avance, estatus, fecha]


# --- 1. Asignar y que caiga en la tabla de la persona -----------------

def test_una_actividad_nueva_recibe_folio_con_el_prefijo_de_la_persona():
    """El folio identifica de quién es la tabla: MIGUEL GALLARDO -> MG-."""
    res = rules.apply_batch_update(
        _matriz(), [{"CONCEPTO": "Cambiar tablero", "_tempId": "t1"}], "MIGUEL GALLARDO")

    assert res.appended == 1
    guardada = res.data[0]
    assert str(guardada.get("FOLIO") or guardada.get("ID")).startswith("MG-")


def test_el_gatekeeper_impide_duplicar_la_misma_alta():
    """
    Dos envíos del mismo `_tempId` —doble clic, reintento de red— tienen que
    dejar una sola fila.
    """
    guardia = rules.Gatekeeper()
    matriz = _matriz()

    primera = rules.apply_batch_update(
        matriz, [{"CONCEPTO": "Una vez", "_tempId": "t-dup"}], "MIGUEL GALLARDO",
        gatekeeper=guardia)
    segunda = rules.apply_batch_update(
        primera.values, [{"CONCEPTO": "Una vez", "_tempId": "t-dup"}], "MIGUEL GALLARDO",
        gatekeeper=guardia)

    assert primera.appended == 1
    assert segunda.appended == 0, "el segundo envío no debe crear otra fila"


def test_la_tarea_se_localiza_por_folio_para_actualizarla():
    matriz = _matriz(_fila(folio="MG-0001", concepto="Cambiar tablero", avance="0"))
    res = rules.apply_batch_update(
        matriz, [{"FOLIO": "MG-0001", "AVANCE": "50"}], "MIGUEL GALLARDO")

    assert res.appended == 0, "actualizar no debe crear una fila nueva"
    fila = next(f for f in res.values if f[0] == "MG-0001")
    assert fila[ENCABEZADOS.index("AVANCE")] == "50"


def test_sin_folio_se_localiza_por_concepto_y_fecha():
    """Respaldo del original cuando el frontend no trae folio."""
    matriz = _matriz(_fila(folio="MG-0001", concepto="Cambiar tablero", fecha="01/03/26"))
    res = rules.apply_batch_update(
        matriz, [{"CONCEPTO": "Cambiar tablero", "FECHA": "01/03/26", "AVANCE": "30"}],
        "MIGUEL GALLARDO")

    assert res.appended == 0
    fila = next(f for f in res.values if f[0] == "MG-0001")
    assert fila[ENCABEZADOS.index("AVANCE")] == "30"


# --- 2. Al 100% pasa a TAREAS REALIZADAS ------------------------------

def test_al_100_la_fila_pasa_debajo_del_separador():
    matriz = _matriz(_fila(folio="MG-0001", concepto="Cambiar tablero", avance="0"))
    res = rules.apply_batch_update(
        matriz, [{"FOLIO": "MG-0001", "AVANCE": "100"}], "MIGUEL GALLARDO")

    assert res.moved is True, "el frontend usa res.moved para mostrar 'Archivado'"

    filas = [f for f in res.values]
    separador = next(i for i, f in enumerate(filas)
                     if rules.ARCHIVE_SEPARATOR in "|".join(str(c) for c in f))
    posicion = next(i for i, f in enumerate(filas) if f[0] == "MG-0001")
    assert posicion > separador, "la tarea terminada va debajo del separador"


def test_una_tarea_a_medias_no_se_archiva():
    matriz = _matriz(_fila(folio="MG-0001", avance="0"))
    res = rules.apply_batch_update(
        matriz, [{"FOLIO": "MG-0001", "AVANCE": "90"}], "MIGUEL GALLARDO")
    assert res.moved is False


def test_un_estatus_terminal_tambien_archiva():
    """No hace falta llegar al 100%: HECHO/CERRADO cierran la tarea."""
    matriz = _matriz(_fila(folio="MG-0001", avance="40"))
    res = rules.apply_batch_update(
        matriz, [{"FOLIO": "MG-0001", "ESTATUS": "HECHO"}], "MIGUEL GALLARDO")
    assert res.moved is True


@pytest.mark.parametrize("valor,completa", [
    ("100", True),
    ("100%", True),
    (100, True),
    (1, True),        # celda con formato de porcentaje: 1 = 100%
    ("1", False),     # texto "1" es 1%, NO 100%
    ("1.0", False),
    ("", False),
])
def test_la_regla_de_100_por_ciento_distingue_1_de_100(valor, completa):
    """
    Invariante del contrato (§5.3 de API_CONTRACT.md): `100`, `'100%'` y el
    **número** 1 son 100%; el **texto** '1' o '1.0' no.

    Confundirlos archivaría como terminada una tarea que va al 1%.
    """
    assert rules.is_progress_complete(valor) is completa


def test_al_archivar_se_sella_la_fecha_de_termino():
    encabezados = ENCABEZADOS + ["FECHA_TERMINO"]
    matriz = [encabezados, ["MG-0001", "X", "", "", "0", "", "01/03/26", ""]]
    res = rules.apply_batch_update(
        matriz, [{"FOLIO": "MG-0001", "AVANCE": "100"}], "MIGUEL GALLARDO")

    fila = next(f for f in res.values if f[0] == "MG-0001")
    assert fila[encabezados.index("FECHA_TERMINO")], "debe quedar la fecha de cierre"


# --- 3. Sincronización en las dos tablas -----------------------------

def test_papa_caliente_reparte_la_tarea_a_cada_involucrado():
    """
    Al delegar desde la tabla de ventas, cada involucrado recibe la fila en su
    propia hoja. Es el "se va a la tabla de la persona asignada".
    """
    tarea = {"FOLIO": "AV-3250", "CONCEPTO": "Cotizar nave",
             "INVOLUCRADOS": "MIGUEL GALLARDO, ROLANDO MORENO",
             # La papa caliente delega **una fase** del proceso (L, CD, EP...),
             # así que el paso es obligatorio: el frontend lo manda como
             # `_assignStep`. Sin él no hay nada que delegar.
             "_assignStep": "CD"}
    hot = rules.apply_hot_potato(rules.SALES_MASTER_SHEET, tarea, {}, "ANTONIA_VENTAS")

    assert hot is not None
    assert hot["workers"] == ["MIGUEL GALLARDO", "ROLANDO MORENO"]
    assert len(hot["rows"]) == 2
    # Todas conservan el folio del original: es lo que permite sincronizar de vuelta.
    for fila in hot["rows"]:
        assert rules.pick_task_value(fila, ["FOLIO", "ID"]) == "AV-3250"
    # Llegan como ASIGNADO y sin avance: es trabajo por hacer, no heredado.
    assert {f["ESTATUS"] for f in hot["rows"]} == {"ASIGNADO"}
    # Y con la fase marcada en el concepto, que es lo que luego permite saber
    # qué paso cerró cada quien.
    assert all("[" in f["CONCEPTO"] for f in hot["rows"])


def test_sin_fase_no_hay_delegacion():
    """Delegar sin decir qué paso se delega no tiene sentido: devuelve None."""
    hot = rules.apply_hot_potato(
        rules.SALES_MASTER_SHEET,
        {"FOLIO": "AV-3250", "INVOLUCRADOS": "MIGUEL GALLARDO"}, {}, "ANTONIA_VENTAS")
    assert hot is None


def test_la_delegacion_no_se_asigna_a_la_propia_hoja_de_origen():
    """Toñita no se delega a sí misma: se filtra de los involucrados."""
    hot = rules.apply_hot_potato(
        rules.SALES_MASTER_SHEET,
        {"FOLIO": "AV-3250", "INVOLUCRADOS": "ANTONIA_VENTAS, MIGUEL GALLARDO",
         "_assignStep": "CD"},
        {}, "ANTONIA_VENTAS")
    assert hot["workers"] == ["MIGUEL GALLARDO"]


@pytest.mark.parametrize("folio,maestra", [
    ("AV-3250", "ANTONIA_VENTAS"),
    ("AP-0012", "ANTONIA PINEDA LOPEZ"),
    ("av-3250", "ANTONIA_VENTAS"),      # el prefijo es insensible a mayúsculas
])
def test_el_prefijo_del_folio_decide_a_que_maestra_se_sincroniza(folio, maestra):
    from api.services.tracker_store import _hoja_maestra_de_folio

    assert _hoja_maestra_de_folio(folio) == maestra


@pytest.mark.parametrize("folio", ["MG-0001", "PPC-99", "", None, "SP-0007"])
def test_un_folio_normal_no_dispara_reverse_sync(folio):
    """Solo las tareas nacidas en las dos maestras se devuelven."""
    from api.services.tracker_store import _hoja_maestra_de_folio

    assert _hoja_maestra_de_folio(folio) is None


def test_reverse_sync_desde_la_hoja_propia_del_trabajador(monkeypatch):
    """
    El caso que estaba roto.

    MIGUEL GALLARDO cierra al 100% una tarea `AV-` que le delegaron. Su hoja se
    llama "MIGUEL GALLARDO" y no contiene "(VENTAS)", que era la condición que
    exigía el código: la sincronización no ocurría y la tabla maestra se quedaba
    con la fase abierta para siempre.
    """
    from api.services import tracker_store

    escrituras = []

    def _falso_persist(sheet_name, tasks, skip_notify=False, username="", persistencia=None):
        escrituras.append({"hoja": sheet_name, "tareas": tasks})
        return rules.BatchResult(_matriz(), [dict(t) for t in tasks], False, 0, [])

    monkeypatch.setattr(tracker_store, "_persist_batch", _falso_persist)
    monkeypatch.setattr(tracker_store, "_persistencia", lambda: None)
    monkeypatch.setattr(tracker_store, "find_row_object", lambda hoja, folio: {})

    tracker_store.save_tracker_batch(
        "MIGUEL GALLARDO",
        [{"FOLIO": "AV-3250", "AVANCE": "100", "ESTATUS": "HECHO"}],
        "MIGUEL_GALLARDO")

    hojas = [e["hoja"] for e in escrituras]
    assert "MIGUEL GALLARDO" in hojas, "primero se guarda en su propia tabla"
    assert rules.SALES_MASTER_SHEET in hojas, (
        "y se sincroniza de vuelta a la maestra de ventas")


def test_reverse_sync_de_folios_ap_a_la_hoja_de_antonia_pineda(monkeypatch):
    """
    Los `AP-` nacen en el tracker personal de Antonia Pineda, que es una hoja
    distinta de la tabla de ventas. No se sincronizaban en absoluto.
    """
    from api.services import tracker_store

    escrituras = []
    monkeypatch.setattr(tracker_store, "_persist_batch",
                        lambda hoja, tareas, skip_notify=False, username="", persistencia=None:
                        escrituras.append(hoja)
                        or rules.BatchResult(_matriz(), [dict(t) for t in tareas], False, 0, []))
    monkeypatch.setattr(tracker_store, "_persistencia", lambda: None)
    monkeypatch.setattr(tracker_store, "find_row_object", lambda hoja, folio: {})

    tracker_store.save_tracker_batch(
        "MIGUEL GALLARDO", [{"FOLIO": "AP-0012", "AVANCE": "100"}], "MIGUEL_GALLARDO")

    assert rules.ANTONIA_PERSONAL_SHEET in escrituras


def test_no_hay_auto_sincronizacion_cuando_ya_se_guarda_en_la_maestra(monkeypatch):
    """Guardar en ANTONIA_VENTAS no debe volver a escribir en ANTONIA_VENTAS."""
    from api.services import tracker_store

    escrituras = []
    monkeypatch.setattr(tracker_store, "_persist_batch",
                        lambda hoja, tareas, skip_notify=False, username="", persistencia=None:
                        escrituras.append(hoja)
                        or rules.BatchResult(_matriz(), [dict(t) for t in tareas], False, 0, []))
    monkeypatch.setattr(tracker_store, "_persistencia", lambda: None)
    monkeypatch.setattr(tracker_store, "find_row_object", lambda hoja, folio: {})
    monkeypatch.setattr(rules, "apply_hot_potato", lambda *a, **k: None)

    tracker_store.save_tracker_batch(
        "ANTONIA_VENTAS", [{"FOLIO": "AV-3250", "AVANCE": "100"}], "ANTONIA_VENTAS")

    assert escrituras.count(rules.SALES_MASTER_SHEET) == 1


def test_una_actividad_asignada_si_lleva_su_avance_a_la_otra_tabla():
    """
    "Se sincroniza en ambas tablas" para una actividad **normal** (sin fase):
    ESTATUS y AVANCE viajan, así que el 100 % de quien la recibió la cierra
    también en la tabla de quien la asignó.

    La papa caliente es el otro caso y va aparte
    (`tests/test_asignacion_bilateral.py`): ahí el 100 % de una microtarea no
    cierra la cotización.
    """
    payload = rules.build_reverse_sync_payload(
        "MIGUEL GALLARDO",
        {"FOLIO": "AV-3250", "AVANCE": "100", "ESTATUS": "HECHO", "CUMPLIMIENTO": "SI"},
        {"CONCEPTO": "Cotizar nave", "AVANCE": "100"},
        {"PROCESO_LOG": "[]"})

    assert payload is not None
    assert payload["AVANCE"] == "100"
    assert payload["ESTATUS"] == "HECHO"
    # CUMPLIMIENTO es del seguimiento del trabajador y no significa lo mismo en
    # la fila maestra: ese sí se filtra siempre.
    assert "CUMPLIMIENTO" not in payload


def test_el_100_de_una_actividad_asignada_archiva_tambien_la_fila_maestra():
    """El cierre completo de una actividad sin fase: pasa a TAREAS REALIZADAS."""
    maestra = _matriz(_fila(folio="AV-3250", concepto="Cotizar nave",
                            avance="40", estatus="EN PROCESO"))
    payload = rules.build_reverse_sync_payload(
        "MIGUEL GALLARDO",
        {"FOLIO": "AV-3250", "AVANCE": "100", "ESTATUS": "HECHO"},
        {"CONCEPTO": "Cotizar nave", "AVANCE": "100"},
        {"PROCESO_LOG": "[]"})

    res = rules.apply_batch_update(maestra, [payload], rules.SALES_MASTER_SHEET,
                                   skip_notify=True)

    assert res.moved is True
    _activas, historial, _ = rules.rows_to_dicts(res.values)
    fila = next(r for r in historial if r.get("FOLIO") == "AV-3250")
    assert fila["AVANCE"] == "100"


def test_pero_el_100_de_una_microtarea_deja_la_venta_abierta():
    """La contraparte: con marca de fase, la venta no se archiva."""
    maestra = _matriz(_fila(folio="AV-3250", concepto="Cotizar nave",
                            avance="40", estatus="EN PROCESO"))
    payload = rules.build_reverse_sync_payload(
        "MIGUEL GALLARDO",
        {"FOLIO": "AV-3250", "AVANCE": "100", "ESTATUS": "HECHO"},
        {"CONCEPTO": "Cotizar nave [Calculo y Diseño]", "AVANCE": "100"},
        {"PROCESO_LOG": "[]"})

    res = rules.apply_batch_update(maestra, [payload], rules.SALES_MASTER_SHEET,
                                   skip_notify=True)

    activas, _historial, _ = rules.rows_to_dicts(res.values)
    assert any(r.get("FOLIO") == "AV-3250" for r in activas)


def test_el_reverse_sync_marca_la_fase_como_terminada():
    payload = rules.build_reverse_sync_payload(
        "MIGUEL GALLARDO",
        {"FOLIO": "AV-3250"},
        {"CONCEPTO": "[CD] Cotizar nave", "AVANCE": "100"},
        {"PROCESO_LOG": "[]"})

    assert '"status": "DONE"' in payload["PROCESO_LOG"]
    assert "🟢 CD" in payload["MAP COT"], "la fase cerrada se pinta en verde"


def test_una_fase_a_medias_queda_en_progreso():
    payload = rules.build_reverse_sync_payload(
        "MIGUEL GALLARDO",
        {"FOLIO": "AV-3250"},
        {"CONCEPTO": "[CD] Cotizar nave", "AVANCE": "40"},
        {"PROCESO_LOG": "[]"})

    assert '"status": "IN_PROGRESS"' in payload["PROCESO_LOG"]
