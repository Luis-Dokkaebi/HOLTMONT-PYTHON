"""Escenarios Gherkin de las reglas de negocio criticas (RESTRICCIONES_EXTREMAS.md R2).

Los `.feature` de `tests/features/` son la fuente de verdad del negocio: los lee
y aprueba una persona que no programa. Este modulo solo los conecta con el motor
real (`api/services/tracker_rules.py`); no reimplementa ninguna regla ni sustituye
por un doble la funcion que se esta probando.

Ejecucion:  python -m pytest tests/test_reglas_negocio_bdd.py -v
"""

from typing import Any, Dict, List, Optional

import pytest
from pydantic import ValidationError
from pytest_bdd import given, parsers, scenarios, then, when

from api.services import tracker_store
from api.services import work_order
from api.services.asignacion import destinos_espejo, es_delegacion_de_fase
from api.services.sheets import SEPARADOR_ARCHIVO, _esta_archivada, _valores_de_tareas
from api.services.tracker_rules import (
    Gatekeeper,
    apply_batch_update,
    build_notification_payload,
    build_reverse_sync_payload,
    is_progress_complete,
    is_sales_sheet,
    SALES_MASTER_SHEET,
    resolve_tracker_target,
)
from backend.core.engines.memoria import MemoryEngine
from backend.schemas.quote import QuoteWrite
from backend.schemas.task import TaskWrite
from backend.schemas.ticket import TicketUpdate, TicketWrite
from backend.services.persistencia import PersistenciaTracker

scenarios("features")


# ----------------------------------------------------------------------
# Andamio de hoja: encabezados reales, con filas de UI encima como en produccion
# ----------------------------------------------------------------------

TRACKER_HEADERS = [
    "ID", "CONCEPTO", "FECHA", "ESTATUS", "AVANCE", "COMENTARIOS",
    "CLASIFICACION", "PRIORIDAD", "FECHA_RESPUESTA", "RESPONSABLE", "CUMPLIMIENTO",
]


def _hoja(filas: Optional[List[Dict[str, Any]]] = None) -> List[List[Any]]:
    """Matriz de una hoja de tracker con dos filas decorativas sobre los encabezados."""
    matriz: List[List[Any]] = [
        ["HOLTMONT - TRACKER PERSONAL"] + [""] * (len(TRACKER_HEADERS) - 1),
        [""] * len(TRACKER_HEADERS),
        list(TRACKER_HEADERS),
    ]
    for fila in filas or []:
        linea: List[Any] = [""] * len(TRACKER_HEADERS)
        for clave, valor in fila.items():
            linea[TRACKER_HEADERS.index(clave)] = valor
        matriz.append(linea)
    return matriz


def _filas_con_concepto(matriz: List[List[Any]], concepto: str) -> List[List[Any]]:
    """Filas de datos cuyo CONCEPTO coincide, sin depender del motor bajo prueba."""
    columna = TRACKER_HEADERS.index("CONCEPTO")
    objetivo = concepto.upper().strip()
    return [
        fila for fila in matriz[3:]
        if len(fila) > columna and str(fila[columna]).upper().strip() == objetivo
    ]


def _valor_de(fila: List[Any], columna: str) -> str:
    return str(fila[TRACKER_HEADERS.index(columna)]).strip()


def _dato_de_ejemplo(crudo: str) -> Any:
    """Convierte una celda de la tabla de Ejemplos al tipo que llega en produccion.

    Entre comillas viaja como texto (lo que teclea una persona); sin comillas es
    el numero nativo que devuelve la hoja de calculo. La distincion es justo la
    regla que este escenario protege.
    """
    limpio = crudo.strip()
    if limpio.startswith('"') and limpio.endswith('"'):
        return limpio[1:-1]
    if "." in limpio:
        return float(limpio)
    return int(limpio)


@pytest.fixture
def contexto() -> Dict[str, Any]:
    """Pizarra compartida entre los pasos de un mismo escenario."""
    return {}


# ----------------------------------------------------------------------
# Ley de Antonia — ruteo y sufijo (VENTAS)
# ----------------------------------------------------------------------

@given(parsers.parse('que el usuario "{usuario}" trabaja en el tracker general'))
def _usuario_en_tracker(contexto: Dict[str, Any], usuario: str) -> None:
    contexto["usuario"] = usuario


@when(parsers.parse('guarda una tarea en la hoja "{hoja}"'))
def _guarda_en_hoja(contexto: Dict[str, Any], hoja: str) -> None:
    contexto["destino"] = resolve_tracker_target(hoja, contexto["usuario"])


@then(parsers.parse('la tarea queda en la hoja "{hoja}"'))
def _tarea_queda_en(contexto: Dict[str, Any], hoja: str) -> None:
    assert contexto["destino"]["sheet"] == hoja


@then(parsers.parse('el sufijo "{sufijo}" desaparece de la hoja destino'))
def _sufijo_desaparece(contexto: Dict[str, Any], sufijo: str) -> None:
    assert sufijo not in contexto["destino"]["sheet"]
    assert contexto["destino"]["redirected"] is True


@then("la hoja destino no fue redirigida")
def _sin_redireccion(contexto: Dict[str, Any]) -> None:
    assert contexto["destino"]["redirected"] is False


@then(parsers.parse('el motivo de la redirección es "{motivo}"'))
def _motivo_redireccion(contexto: Dict[str, Any], motivo: str) -> None:
    assert contexto["destino"]["redirected"] is True
    assert contexto["destino"]["reason"] == motivo


# ----------------------------------------------------------------------
# AVANCE — el 1 nativo de la hoja es 100 %
# ----------------------------------------------------------------------

@given(parsers.parse("que la casilla AVANCE de una tarea contiene {valor}"))
def _avance_contiene(contexto: Dict[str, Any], valor: str) -> None:
    contexto["avance"] = _dato_de_ejemplo(valor)


@when("el sistema evalúa si la tarea está terminada")
def _evalua_avance(contexto: Dict[str, Any]) -> None:
    contexto["terminada"] = is_progress_complete(contexto["avance"])


@then(parsers.parse("la respuesta es {terminada}"))
def _respuesta_avance(contexto: Dict[str, Any], terminada: str) -> None:
    assert contexto["terminada"] is (terminada.strip() == "sí")


# ----------------------------------------------------------------------
# Anti-duplicacion — gatekeeper por identificador temporal y rescate por CONCEPTO+FECHA
# ----------------------------------------------------------------------

@given(parsers.parse(
    'que una tarea nueva "{concepto}" lleva el identificador temporal "{temp_id}"'
))
def _tarea_con_temp_id(contexto: Dict[str, Any], concepto: str, temp_id: str) -> None:
    contexto["matriz"] = _hoja()
    contexto["candado"] = Gatekeeper()
    contexto["tarea"] = {
        "CONCEPTO": concepto, "FECHA": "06/07/26", "ESTATUS": "PENDIENTE", "_tempId": temp_id,
    }
    contexto["concepto"] = concepto


def _enviar(contexto: Dict[str, Any], veces: int) -> None:
    for _ in range(veces):
        resultado = apply_batch_update(
            contexto["matriz"], [dict(contexto["tarea"])], "JAIME OLIVO",
            gatekeeper=contexto["candado"],
        )
        contexto["matriz"] = resultado.values
        contexto["resultado"] = resultado


@when("el formulario se envía cinco veces seguidas sin esperar respuesta")
def _envia_cinco_veces(contexto: Dict[str, Any]) -> None:
    _enviar(contexto, 5)


@when("el formulario se envía una vez")
def _envia_una_vez(contexto: Dict[str, Any]) -> None:
    _enviar(contexto, 1)


@then(parsers.parse('existe exactamente una fila con el concepto "{concepto}"'))
def _una_sola_fila(contexto: Dict[str, Any], concepto: str) -> None:
    assert len(_filas_con_concepto(contexto["matriz"], concepto)) == 1


@then("el sistema devuelve la tarea guardada con su FOLIO asignado")
def _devuelve_tarea_guardada(contexto: Dict[str, Any]) -> None:
    devuelta = contexto["resultado"].data
    assert len(devuelta) == 1
    folio = str(devuelta[0]["FOLIO"]).strip()
    assert folio.startswith("JO-")
    fila = _filas_con_concepto(contexto["matriz"], contexto["concepto"])[0]
    assert _valor_de(fila, "ID") == folio


@given(parsers.parse(
    'que existe una tarea "{concepto}" con fecha "{fecha}" a cargo de "{responsable}"'
))
def _tarea_existente(contexto: Dict[str, Any], concepto: str, fecha: str, responsable: str) -> None:
    contexto["matriz"] = _hoja([{
        "ID": "", "CONCEPTO": concepto, "FECHA": fecha,
        "RESPONSABLE": responsable, "ESTATUS": "PENDIENTE",
    }])
    contexto["candado"] = Gatekeeper()
    contexto["concepto"] = concepto
    contexto["fecha"] = fecha
    contexto["responsable"] = responsable


@given("que esa tarea se quedó sin FOLIO por un error de escritura")
def _tarea_sin_folio(contexto: Dict[str, Any]) -> None:
    fila = _filas_con_concepto(contexto["matriz"], contexto["concepto"])[0]
    assert _valor_de(fila, "ID") == ""


@when(parsers.parse(
    'llega una actualización para esa misma tarea con el comentario "{comentario}"'
))
def _llega_actualizacion(contexto: Dict[str, Any], comentario: str) -> None:
    resultado = apply_batch_update(contexto["matriz"], [{
        "CONCEPTO": contexto["concepto"], "FECHA": contexto["fecha"],
        "RESPONSABLE": contexto["responsable"], "COMENTARIOS": comentario,
    }], "JAIME OLIVO", gatekeeper=contexto["candado"])
    contexto["matriz"] = resultado.values
    contexto["resultado"] = resultado


@then(parsers.parse('la fila conserva el comentario "{comentario}"'))
def _conserva_comentario(contexto: Dict[str, Any], comentario: str) -> None:
    fila = _filas_con_concepto(contexto["matriz"], contexto["concepto"])[0]
    assert _valor_de(fila, "COMENTARIOS") == comentario
    assert _valor_de(fila, "ESTATUS") == "PENDIENTE"


# ----------------------------------------------------------------------
# Reverse sync — las tareas con FOLIO AV- vuelven a la tabla maestra
# ----------------------------------------------------------------------

@given(parsers.parse('que la tarea "{concepto}" tiene el FOLIO "{folio}"'))
def _tarea_de_ventas(contexto: Dict[str, Any], concepto: str, folio: str) -> None:
    contexto["tarea"] = {"FOLIO": folio, "CONCEPTO": concepto}
    contexto["folio"] = folio


@given(parsers.parse('que la tarea "{concepto}" no tiene FOLIO'))
def _tarea_sin_folio_maestro(contexto: Dict[str, Any], concepto: str) -> None:
    contexto["tarea"] = {"CONCEPTO": concepto}
    contexto["folio"] = ""


@when(parsers.parse('"{companero}" la deja con ESTATUS "{estatus}" y AVANCE {avance:d}'))
def _companero_actualiza(
    contexto: Dict[str, Any], companero: str, estatus: str, avance: int
) -> None:
    tarea = dict(contexto["tarea"])
    tarea.update({"ESTATUS": estatus, "AVANCE": avance, "CUMPLIMIENTO": "SI"})
    contexto["hacia_maestra"] = build_reverse_sync_payload(
        companero, tarea, worker_row={"CONCEPTO": tarea["CONCEPTO"], "AVANCE": avance,
                                      "ESTATUS": estatus},
    )


@then(parsers.parse('la tabla maestra recibe el ESTATUS "{estatus}"'))
def _maestra_recibe_estatus(contexto: Dict[str, Any], estatus: str) -> None:
    assert contexto["hacia_maestra"]["ESTATUS"] == estatus


@then(parsers.parse('la tabla maestra conserva el mismo FOLIO "{folio}"'))
def _maestra_conserva_folio(contexto: Dict[str, Any], folio: str) -> None:
    assert contexto["hacia_maestra"]["FOLIO"] == folio


@then(parsers.parse('la tabla maestra no recibe la casilla "{casilla}"'))
def _maestra_sin_casilla(contexto: Dict[str, Any], casilla: str) -> None:
    assert casilla not in contexto["hacia_maestra"]


@then("el sistema no envía nada a la tabla maestra")
def _sin_envio_a_maestra(contexto: Dict[str, Any]) -> None:
    assert contexto["hacia_maestra"] is None


# ----------------------------------------------------------------------
# Integraciones — fecha completa hacia el correo de avisos
# ----------------------------------------------------------------------

@given(parsers.parse('que una tarea "{concepto}" inicia el "{fecha}"'))
def _tarea_con_fecha(contexto: Dict[str, Any], concepto: str, fecha: str) -> None:
    contexto["tarea"] = {"CONCEPTO": concepto, "FECHA": fecha, "RESPONSABLE": "JAIME OLIVO"}


@when("el sistema prepara el aviso para esa tarea")
def _prepara_aviso(contexto: Dict[str, Any]) -> None:
    contexto["aviso"] = build_notification_payload("JAIME OLIVO", contexto["tarea"])


@then(parsers.parse('la fecha de inicio del aviso termina en "{final}"'))
def _aviso_termina_en(contexto: Dict[str, Any], final: str) -> None:
    assert contexto["aviso"]["fechaInicio"].endswith(final)


@then("la fecha de inicio del aviso conserva los milisegundos")
def _aviso_con_milisegundos(contexto: Dict[str, Any]) -> None:
    inicio = contexto["aviso"]["fechaInicio"]
    milisegundos = inicio.split(".")[-1].rstrip("Z")
    assert len(milisegundos) == 3
    assert milisegundos.isdigit()


@then(parsers.parse('el aviso menciona el concepto "{concepto}"'))
def _aviso_menciona_concepto(contexto: Dict[str, Any], concepto: str) -> None:
    assert contexto["aviso"]["concepto"] == concepto


# ----------------------------------------------------------------------
# Valores de respaldo en casillas con lista desplegable
# ----------------------------------------------------------------------

@given(parsers.parse('que llega una tarea nueva "{concepto}" sin ESTATUS'))
def _tarea_sin_estatus(contexto: Dict[str, Any], concepto: str) -> None:
    contexto["matriz"] = _hoja()
    contexto["candado"] = Gatekeeper()
    contexto["concepto"] = concepto
    contexto["tarea"] = {"CONCEPTO": concepto, "FECHA": "05/08/26"}


@given(parsers.parse('que llega una tarea nueva "{concepto}" con ESTATUS "{estatus}"'))
def _tarea_con_estatus(contexto: Dict[str, Any], concepto: str, estatus: str) -> None:
    contexto["matriz"] = _hoja()
    contexto["candado"] = Gatekeeper()
    contexto["concepto"] = concepto
    contexto["tarea"] = {"CONCEPTO": concepto, "FECHA": "05/08/26", "ESTATUS": estatus}


@when(parsers.parse('el sistema la guarda en la hoja "{hoja}"'))
def _guarda_tarea(contexto: Dict[str, Any], hoja: str) -> None:
    resultado = apply_batch_update(
        contexto["matriz"], [dict(contexto["tarea"])], hoja, gatekeeper=contexto["candado"],
    )
    contexto["matriz"] = resultado.values
    contexto["resultado"] = resultado


@then(parsers.parse('la fila guardada tiene ESTATUS "{estatus}"'))
def _fila_con_estatus(contexto: Dict[str, Any], estatus: str) -> None:
    filas = _filas_con_concepto(contexto["matriz"], contexto["concepto"])
    assert len(filas) == 1
    assert _valor_de(filas[0], "ESTATUS") == estatus


# ----------------------------------------------------------------------
# A dónde va una cotización asignada
# ----------------------------------------------------------------------

@given(parsers.parse('que Toñita reparte una cotización a "{destinatario}"'))
def _tonita_reparte(contexto: Dict[str, Any], destinatario: str) -> None:
    contexto["destinos"] = destinos_espejo(
        SALES_MASTER_SHEET, {"VENDEDOR": destinatario}, username=SALES_MASTER_SHEET)


@given(parsers.parse(
    'que el vendedor "{vendedor}" reparte una cotización a "{destinatario}"'))
def _vendedor_reparte(contexto: Dict[str, Any], vendedor: str, destinatario: str) -> None:
    contexto["destinos"] = destinos_espejo(
        f"{vendedor} (VENTAS)", {"VENDEDOR": destinatario}, username=vendedor)


@given(parsers.parse('que "{quien}" asigna una actividad a "{destinatario}"'))
def _asigna_actividad(contexto: Dict[str, Any], quien: str, destinatario: str) -> None:
    contexto["destinos"] = destinos_espejo(
        quien, {"INVOLUCRADOS": destinatario}, username=quien)


@then(parsers.parse('la copia va a la tabla "{tabla}"'))
def _copia_va_a(contexto: Dict[str, Any], tabla: str) -> None:
    assert contexto["destinos"] == [tabla]


@then("no hay ninguna tabla destino")
def _sin_destino(contexto: Dict[str, Any]) -> None:
    assert contexto["destinos"] == [], (
        f"sin tabla (VENTAS) no hay destino, y se resolvió {contexto['destinos']}"
    )


# ----------------------------------------------------------------------
# Una celda numérica en una columna de texto
# ----------------------------------------------------------------------

@given(parsers.parse("que llega una cotización nueva con RELOJ numérico {valor:d}"))
def _cotizacion_con_reloj_numerico(contexto: Dict[str, Any], valor: int) -> None:
    contexto["modelo"] = QuoteWrite
    contexto["fila"] = {"FOLIO": "AV-1", "RELOJ": valor}


@given(parsers.parse("que llega una actividad con RELOJ numérico {valor:d}"))
def _actividad_con_reloj_numerico(contexto: Dict[str, Any], valor: int) -> None:
    contexto["modelo"] = TaskWrite
    contexto["fila"] = {"FOLIO": "JO-1", "RELOJ": valor}


@given(parsers.parse('que llega una actividad con RELOJ de texto "{valor}"'))
def _actividad_con_reloj_de_texto(contexto: Dict[str, Any], valor: str) -> None:
    contexto["modelo"] = TaskWrite
    contexto["fila"] = {"FOLIO": "JO-1", "RELOJ": valor}


@when("el sistema la valida para guardarla")
def _valida_la_fila(contexto: Dict[str, Any]) -> None:
    contexto["validada"] = contexto["modelo"].desde_hoja(contexto["fila"])


@then(parsers.parse('se acepta y RELOJ vale "{esperado}"'))
def _reloj_vale(contexto: Dict[str, Any], esperado: str) -> None:
    assert contexto["validada"].reloj == esperado


@given(parsers.parse(
    'que la actividad "{concepto}" está al 0 % con RELOJ numérico {reloj:d}'))
def _actividad_abierta_con_reloj(contexto: Dict[str, Any], concepto: str, reloj: int) -> None:
    contexto["concepto"] = concepto
    contexto["reloj"] = reloj
    contexto["motor"] = MemoryEngine({
        "tasks": [{
            "id": "11111111-1111-1111-1111-111111111111",
            "dedupe_key": "JAIME OLIVO::JO-0001", "folio": "JO-0001",
            "source_sheet": "JAIME OLIVO", "concepto": concepto,
            "avance": 0.0, "status": "ASIGNADO", "reloj": str(reloj),
        }],
        "quotes": [], "people": [], "plan_semanal": [],
        "task_involucrados": [], "system_log": [],
    })


@when("el usuario le pone 100 % y guarda")
def _cierra_al_cien(contexto: Dict[str, Any], monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(tracker_store, "_persistencia",
                        lambda: PersistenciaTracker(contexto["motor"]))
    monkeypatch.setattr(tracker_store, "read_values",
                        lambda hoja: [["FOLIO", "CONCEPTO", "AVANCE", "ESTATUS", "RELOJ"]])
    contexto["respuesta"] = tracker_store.save_tracker_batch(
        "JAIME OLIVO",
        [{"FOLIO": "JO-0001", "CONCEPTO": contexto["concepto"],
          "AVANCE": "100", "ESTATUS": "ASIGNADO", "RELOJ": contexto["reloj"]}],
        username="JAIME_OLIVO",
    )


@then("la actividad queda bajo TAREAS REALIZADAS")
def _queda_archivada(contexto: Dict[str, Any]) -> None:
    assert contexto["respuesta"]["success"] is True, contexto["respuesta"].get("message")
    valores = _valores_de_tareas(contexto["motor"].select("tasks"))
    assert any(SEPARADOR_ARCHIVO in celda for celda in valores[1]), (
        f"la tarea al 100 % no quedó bajo {SEPARADOR_ARCHIVO}: {valores}"
    )


# ----------------------------------------------------------------------
# La Pre Work Order reparte su programa en el Tracker
# ----------------------------------------------------------------------

@given("un programa de Pre Work Order con los renglones:")
def _programa_de_pwo(contexto: Dict[str, Any], datatable: List[List[str]]) -> None:
    """La tabla del escenario, tal como la manda el formulario."""
    encabezados, *filas = datatable
    contexto["programa"] = [
        {
            "description": celda[encabezados.index("descripcion")].strip(),
            "seccion": celda[encabezados.index("seccion")].strip(),
            "responsable": celda[encabezados.index("responsable")].strip(),
        }
        for celda in filas
    ]


@when("la orden se reparte en el Tracker")
def _reparte_el_programa(contexto: Dict[str, Any]) -> None:
    contexto["reparto"] = work_order.tareas_de_programa(
        contexto["programa"],
        {"FOLIO": "1001AC Electro 060826", "AREA": "ELECTROMECANICA",
         "CLASIFICACION": "AA", "FECHA": "06/08/26"},
    )


@then(parsers.parse('"{persona}" recibe la tarea "{descripcion}" en su tracker'))
def _recibe_la_tarea(contexto: Dict[str, Any], persona: str, descripcion: str) -> None:
    suyas = [fila for hoja, fila in contexto["reparto"] if hoja == persona]
    assert suyas, f"{persona} no recibió ninguna tarea: {contexto['reparto']}"
    assert any(fila["CONCEPTO"].startswith(descripcion) for fila in suyas), (
        f"{persona} no recibió «{descripcion}»: {[f['CONCEPTO'] for f in suyas]}")


@then(parsers.parse("el reparto produce {cuantas:d} tareas"))
def _cuantas_tareas(contexto: Dict[str, Any], cuantas: int) -> None:
    assert len(contexto["reparto"]) == cuantas, contexto["reparto"]


@then("ninguna tarea del reparto cae en una tabla de ventas")
def _ninguna_en_ventas(contexto: Dict[str, Any]) -> None:
    for hoja, _ in contexto["reparto"]:
        assert not is_sales_sheet(hoja), f"la línea se filtró a {hoja}"


@then("ninguna tarea del reparto se toma por una fase de papa caliente")
def _ninguna_es_fase(contexto: Dict[str, Any]) -> None:
    for _, fila in contexto["reparto"]:
        assert es_delegacion_de_fase(fila) is False, fila["CONCEPTO"]


# Los renglones de un programa comparten el folio de la orden pero son trabajos
# distintos, de personas distintas. Confundirlos con copias de una misma
# actividad hacía que el 100 % de uno cerrara el de otro, y que el avance de otro
# devolviera a operativo lo ya terminado. Ver `tests/test_actividades_que_regresan.py`.

FOLIO_DE_LA_ORDEN = "1001AC Electro 060826"


@given(parsers.parse(
    'que la orden repartió "{una}" a "{persona_una}" y "{otra}" a "{persona_otra}"'))
def _orden_repartida(contexto: Dict[str, Any], monkeypatch: pytest.MonkeyPatch,
                     una: str, persona_una: str, otra: str, persona_otra: str) -> None:
    from api.services.asignacion import clave_de_copia

    reparto = work_order.tareas_de_programa(
        [{"description": una, "seccion": "TRABAJO", "responsable": persona_una},
         {"description": otra, "seccion": "TRABAJO", "responsable": persona_otra}],
        {"FOLIO": FOLIO_DE_LA_ORDEN, "AREA": "ELECTROMECANICA",
         "CLASIFICACION": "AA", "FECHA": "06/08/26"},
    )
    assert len(reparto) == 2, reparto

    contexto["renglones"] = {}
    filas = []
    for n, (hoja, fila) in enumerate(reparto, start=1):
        contexto["renglones"][fila["CONCEPTO"].split(" [")[0]] = {
            "hoja": hoja, "concepto": fila["CONCEPTO"],
            "responsable": fila["INVOLUCRADOS"],
        }
        filas.append({
            "id": f"2222222{n}-2222-2222-2222-22222222222{n}",
            "dedupe_key": clave_de_copia(FOLIO_DE_LA_ORDEN, hoja),
            "folio": FOLIO_DE_LA_ORDEN, "source_sheet": hoja,
            "concepto": fila["CONCEPTO"], "assignee_raw": fila["INVOLUCRADOS"],
            "avance": 0.0, "status": "ASIGNADO", "folio_sintetico": False,
            "created_at": f"2026-08-0{n}T00:00:00Z",
        })

    contexto["motor"] = MemoryEngine({
        "tasks": filas, "quotes": [], "people": [], "plan_semanal": [],
        "task_involucrados": [], "system_log": [],
    })
    monkeypatch.setattr(tracker_store, "_persistencia",
                        lambda: PersistenciaTracker(contexto["motor"]))
    monkeypatch.setattr(
        tracker_store, "read_values",
        lambda hoja: [["FOLIO", "CONCEPTO", "INVOLUCRADOS", "AVANCE", "ESTATUS"]])


@when(parsers.parse('"{persona}" deja "{descripcion}" al {avance:d} %'))
def _deja_su_renglon(contexto: Dict[str, Any], persona: str,
                     descripcion: str, avance: int) -> None:
    renglon = contexto["renglones"][descripcion]
    assert renglon["hoja"] == persona, (
        f"«{descripcion}» es de {renglon['hoja']}, no de {persona}")
    contexto["respuesta"] = tracker_store.save_tracker_batch(
        renglon["hoja"],
        [{"FOLIO": FOLIO_DE_LA_ORDEN, "CONCEPTO": renglon["concepto"],
          "INVOLUCRADOS": renglon["responsable"], "AVANCE": str(avance)}],
        username=persona.replace(" ", "_"),
    )
    assert contexto["respuesta"]["success"] is True, contexto["respuesta"].get("message")


def _fila_del_renglon(contexto: Dict[str, Any], descripcion: str) -> Dict[str, Any]:
    renglon = contexto["renglones"][descripcion]
    return next(f for f in contexto["motor"].select("tasks")
                if f["source_sheet"] == renglon["hoja"])


@then(parsers.parse('"{descripcion}" queda terminada'))
def _renglon_terminado(contexto: Dict[str, Any], descripcion: str) -> None:
    fila = _fila_del_renglon(contexto, descripcion)
    assert _esta_archivada(fila) is True, fila


@then(parsers.parse('"{descripcion}" sigue en operativo con su propio avance'))
def _renglon_intacto(contexto: Dict[str, Any], descripcion: str) -> None:
    fila = _fila_del_renglon(contexto, descripcion)
    assert _esta_archivada(fila) is False, (
        f"«{descripcion}» se archivó sin que su responsable la tocara: {fila}")
    assert fila["avance"] == 0.0, f"su avance se pisó con el de otro renglón: {fila}"


@given(parsers.parse('una Pre Work Order con clasificación "{clase}"'))
def _pwo_con_clasificacion(contexto: Dict[str, Any], clase: str) -> None:
    contexto["motor"] = MemoryEngine({
        "tasks": [], "quotes": [], "people": [], "plan_semanal": [],
        "task_involucrados": [], "system_log": [], "work_orders": [],
    })
    contexto["orden"] = {
        "cliente": "ACME CORP", "especialidad": "ELECTROMECANICA",
        "concepto": "LEVANTAMIENTO DE NAVE", "clasificacion": clase,
        "responsable": "TERESA GARZA",
    }


@when("se guarda la orden")
def _guarda_la_orden(contexto: Dict[str, Any], monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(work_order, "_persistencia",
                        lambda: PersistenciaTracker(contexto["motor"]))
    monkeypatch.setattr(work_order, "_engine", lambda: contexto["motor"])
    monkeypatch.setattr(work_order, "save_to_obsidian", lambda *a, **k: None)
    monkeypatch.setattr(work_order, "get_next_sequence", lambda *a, **k: "1001")
    contexto["respuesta"] = work_order.process_and_save_work_order(
        [contexto["orden"]], "PREWORK_ORDER")


@then("el guardado falla avisando de la clasificación")
def _falla_por_clasificacion(contexto: Dict[str, Any]) -> None:
    assert contexto["respuesta"]["success"] is False
    assert "CLASIFICACION" in contexto["respuesta"]["message"].upper()


@then("no queda ninguna tarea guardada")
def _sin_tareas(contexto: Dict[str, Any]) -> None:
    assert contexto["motor"].select("tasks") == []


# ----------------------------------------------------------------------
# Una persona, un tracker
# ----------------------------------------------------------------------

@given(parsers.parse('que "{directorio}" es el nombre de directorio de "{hoja}"'))
def _persona_con_dos_nombres(contexto: Dict[str, Any], directorio: str, hoja: str) -> None:
    """
    El directorio (`people`) la registra con su nombre completo y su tracker se
    llama como dice el organigrama. Los dos nombres son suyos.
    """
    contexto["motor"] = MemoryEngine({
        "tasks": [], "quotes": [],
        "people": [{"id": "p-1", "nombre": directorio, "departamento": "COMPRAS"}],
        "profiles": [], "plan_semanal": [], "task_involucrados": [],
        "system_log": [], "work_orders": [],
    })
    contexto["hoja_de_la_persona"] = hoja


@when(parsers.parse('se captura la actividad "{concepto}" a cargo de "{responsable}"'))
def _captura_actividad(contexto: Dict[str, Any], concepto: str, responsable: str,
                       monkeypatch: pytest.MonkeyPatch) -> None:
    """La cola de "Agregar Actividad", tal como la manda `submitBatch`."""
    monkeypatch.setattr(work_order, "_persistencia",
                        lambda: PersistenciaTracker(contexto["motor"]))
    monkeypatch.setattr(work_order, "_engine", lambda: contexto["motor"])
    monkeypatch.setattr(work_order, "save_to_obsidian", lambda *a, **k: None)
    contexto["respuesta"] = work_order.process_and_save_work_order(
        [{"id": "PPC-800001", "concepto": concepto, "responsable": responsable,
          "especialidad": "COMPRAS", "clasificacion": "A", "cumplimiento": "NO"}],
        "VANESSA_DE_LARA")


@then(parsers.parse('la actividad queda en la hoja "{hoja}"'))
def _actividad_en_la_hoja(contexto: Dict[str, Any], hoja: str) -> None:
    assert contexto["respuesta"]["success"] is True, contexto["respuesta"].get("message")
    hojas = sorted({f["source_sheet"] for f in contexto["motor"].select("tasks")})
    assert hojas == [hoja], f"la actividad quedó en {hojas} y se esperaba {[hoja]}"


@when(parsers.parse('se captura la actividad "{concepto}" sin responsable'))
def _captura_actividad_sin_responsable(contexto: Dict[str, Any], concepto: str,
                                       monkeypatch: pytest.MonkeyPatch) -> None:
    _captura_actividad(contexto, concepto, "", monkeypatch)


# ----------------------------------------------------------------------
# Tickets de bugs — la evidencia no se altera
# ----------------------------------------------------------------------
#
# Estos pasos ejercen `TicketRepository` de verdad, sobre `MemoryEngine`. Lo
# que se protege aquí es la razón por la que el dueño pidió el sistema: que el
# video de un reporte quede como se subió. Por eso el escenario del rechazo
# comprueba el modelo de escritura (`TicketUpdate`), que es el único camino que
# tiene quien resuelve, y no un mensaje de error de la vista.

@given(parsers.parse('que {quien} reporta el problema "{descripcion}" en el módulo "{modulo}"'))
def _reporta_un_bug(contexto: Dict[str, Any], quien: str, descripcion: str, modulo: str) -> None:
    from backend.repositories.tickets import TicketRepository

    contexto["motor"] = MemoryEngine({"bug_tickets": [], "ticket_notificaciones": []})
    contexto["tickets"] = TicketRepository(contexto["motor"])
    contexto["reportante"] = quien
    contexto["descripcion"] = descripcion
    contexto["modulo"] = modulo


@when("el reporte se envía")
def _envia_el_reporte(contexto: Dict[str, Any]) -> None:
    contexto["ticket"] = contexto["tickets"].crear(
        TicketWrite(modulo=contexto["modulo"], descripcion=contexto["descripcion"]),
        reportado_por=contexto["reportante"],
    )


def _asegurar_ticket(contexto: Dict[str, Any]) -> None:
    """Los escenarios que no dicen "se envía" igual necesitan el ticket creado."""
    if "ticket" not in contexto:
        _envia_el_reporte(contexto)


@then(parsers.parse('el ticket queda con estatus "{estatus}"'))
def _ticket_con_estatus(contexto: Dict[str, Any], estatus: str) -> None:
    _asegurar_ticket(contexto)
    assert contexto["ticket"].estatus == estatus


@then(parsers.parse('el ticket queda a nombre de "{quien}"'))
def _ticket_a_nombre_de(contexto: Dict[str, Any], quien: str) -> None:
    assert contexto["ticket"].reportado_por == quien


@when("quien resuelve intenta cambiar la descripción del ticket")
def _intenta_reescribir_la_descripcion(contexto: Dict[str, Any]) -> None:
    _asegurar_ticket(contexto)
    try:
        TicketUpdate(estatus="EN_REVISION", descripcion="otra cosa")
        contexto["rechazado"] = False
    except ValidationError:
        contexto["rechazado"] = True


@then("el sistema rechaza el cambio")
def _el_sistema_rechaza(contexto: Dict[str, Any]) -> None:
    assert contexto["rechazado"] is True, "se aceptó reescribir la descripción del reporte"


@then(parsers.parse('la descripción sigue siendo "{descripcion}"'))
def _descripcion_intacta(contexto: Dict[str, Any], descripcion: str) -> None:
    almacenado = contexto["tickets"].obtener(contexto["ticket"].folio)
    assert almacenado.descripcion == descripcion


@given(parsers.parse('que al ticket se le adjunta la evidencia "{archivo}"'))
def _adjunta_evidencia(contexto: Dict[str, Any], archivo: str) -> None:
    _asegurar_ticket(contexto)
    contexto["tickets"].agregar_evidencia(
        contexto["ticket"].folio,
        {"url": f"https://storage.local/{archivo}", "tipo": "video/mp4", "sha256": "abc"},
    )


@when(parsers.parse('se adjunta al ticket una segunda evidencia "{archivo}"'))
def _adjunta_segunda_evidencia(contexto: Dict[str, Any], archivo: str) -> None:
    contexto["ticket"] = contexto["tickets"].agregar_evidencia(
        contexto["ticket"].folio,
        {"url": f"https://storage.local/{archivo}", "tipo": "image/png", "sha256": "def"},
    )


@then("el ticket conserva las dos evidencias en el orden en que se subieron")
def _dos_evidencias_en_orden(contexto: Dict[str, Any]) -> None:
    almacenado = contexto["tickets"].obtener(contexto["ticket"].folio)
    assert len(almacenado.evidencia) == 2, f"quedaron {len(almacenado.evidencia)} evidencias"
    assert almacenado.evidencia[0]["url"].endswith("video-original.mp4")
    assert almacenado.evidencia[1]["url"].endswith("captura-extra.png")


@then(parsers.parse('la evidencia "{archivo}" sigue estando'))
def _la_evidencia_sigue(contexto: Dict[str, Any], archivo: str) -> None:
    almacenado = contexto["tickets"].obtener(contexto["ticket"].folio)
    urls = [e["url"] for e in almacenado.evidencia]
    assert any(u.endswith(archivo) for u in urls), f"{archivo} ya no está en {urls}"


@when(parsers.parse('{quien} marca el ticket como "{estatus}"'))
def _marca_el_ticket(contexto: Dict[str, Any], quien: str, estatus: str) -> None:
    _asegurar_ticket(contexto)
    contexto["ticket"] = contexto["tickets"].actualizar_estatus(
        contexto["ticket"].folio, TicketUpdate(estatus=estatus, resuelto_por=quien))


@then(parsers.parse('el ticket queda a cargo de "{quien}" con su fecha de resolución'))
def _ticket_resuelto_por(contexto: Dict[str, Any], quien: str) -> None:
    assert contexto["ticket"].resuelto_por == quien
    assert contexto["ticket"].resuelto_en is not None


# ----------------------------------------------------------------------
# Avisos a quien reporta un bug
# ----------------------------------------------------------------------
#
# El canal es dentro de la plataforma, no correo: de las 41 cuentas del
# organigrama solo 6 tienen correo registrado, así que un aviso por correo no
# le llegaría a 35 personas y fallaría en silencio.

@given("que el sistema de avisos está caído")
def _avisos_caidos(contexto: Dict[str, Any]) -> None:
    """La tabla de avisos no existe o la base no responde."""
    from backend.core.errors import ErrorDeMotor

    motor = contexto["motor"]
    original = motor.insertar

    def falla_solo_en_avisos(tabla, filas):
        if tabla == "ticket_notificaciones":
            raise ErrorDeMotor("la tabla de avisos no existe", codigo="PGRST205")
        return original(tabla, filas)

    motor.insertar = falla_solo_en_avisos


@when(parsers.parse("{quien} lee sus avisos"))
def _lee_sus_avisos(contexto: Dict[str, Any], quien: str) -> None:
    _asegurar_ticket(contexto)
    contexto["tickets"].notificaciones.marcar_leidas(quien)


@then(parsers.parse("{quien} tiene {cuantos:d} aviso sin leer"))
@then(parsers.parse("{quien} tiene {cuantos:d} avisos sin leer"))
def _avisos_sin_leer(contexto: Dict[str, Any], quien: str, cuantos: int) -> None:
    _asegurar_ticket(contexto)
    reales = contexto["tickets"].notificaciones.contar_no_leidas(quien)
    assert reales == cuantos, f"{quien} tiene {reales} avisos sin leer, se esperaban {cuantos}"


@then(parsers.parse('su aviso más reciente dice "{fragmento}"'))
def _aviso_reciente_dice(contexto: Dict[str, Any], fragmento: str) -> None:
    bandeja = contexto["tickets"].notificaciones.listar(contexto["reportante"])
    assert bandeja, "no hay ningún aviso en la bandeja"
    assert fragmento in bandeja[0].mensaje, (
        f"el aviso dice {bandeja[0].mensaje!r} y se esperaba que incluyera {fragmento!r}")
