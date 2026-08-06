"""Escenarios Gherkin de las reglas de negocio criticas (RESTRICCIONES_EXTREMAS.md R2).

Los `.feature` de `tests/features/` son la fuente de verdad del negocio: los lee
y aprueba una persona que no programa. Este modulo solo los conecta con el motor
real (`api/services/tracker_rules.py`); no reimplementa ninguna regla ni sustituye
por un doble la funcion que se esta probando.

Ejecucion:  python -m pytest tests/test_reglas_negocio_bdd.py -v
"""

from typing import Any, Dict, List, Optional

import pytest
from pytest_bdd import given, parsers, scenarios, then, when

from api.services.asignacion import destinos_espejo
from api.services.tracker_rules import (
    Gatekeeper,
    apply_batch_update,
    build_notification_payload,
    build_reverse_sync_payload,
    is_progress_complete,
    SALES_MASTER_SHEET,
    resolve_tracker_target,
)

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
