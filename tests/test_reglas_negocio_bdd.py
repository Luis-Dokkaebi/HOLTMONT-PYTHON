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

from api.services import agente_sql
from api.services import agente_sql_correo as agente_correo
from api.services import agente_sql_esquemas as agente_esquemas
from api.services import prospeccion
from api.services import tracker_store
from api.services import work_order
from api.services.denue_repo import RepositorioDenue
from api.services.asignacion import destinos_espejo, es_delegacion_de_fase
from api.services.sheets import SEPARADOR_ARCHIVO, _valores_de_tareas
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
from backend.repositories.geo_prospectos import (
    TABLA as TABLA_PROSPECTOS,
    GeoProspectoRepository,
    ProspectoNoEncontrado,
)
from backend.schemas.geo_prospecto import ProspectoWrite
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


@given(parsers.parse('que "{cuenta}" entra al sistema'))
def _entra_al_sistema(contexto: Dict[str, Any], cuenta: str) -> None:
    from api.main import api_get_system_config
    from api.services import organigrama

    contexto["config"] = api_get_system_config(
        role=organigrama.perfil(cuenta).get("role", "STAFF_USER"), username=cuenta)


def _modulos_por_etiqueta(contexto: Dict[str, Any], etiqueta: str) -> list:
    return [m for m in contexto["config"]["specialModules"] if m["label"] == etiqueta]


@then(parsers.parse('ve el módulo "{etiqueta}" apuntando a "{destino}"'))
def _ve_el_modulo(contexto: Dict[str, Any], etiqueta: str, destino: str) -> None:
    modulos = _modulos_por_etiqueta(contexto, etiqueta)
    assert modulos, f"no ve «{etiqueta}»; ve {[m['label'] for m in contexto['config']['specialModules']]}"
    assert modulos[0]["target"] == destino


@then(parsers.parse('no ve el módulo "{etiqueta}"'))
def _no_ve_el_modulo(contexto: Dict[str, Any], etiqueta: str) -> None:
    assert not _modulos_por_etiqueta(contexto, etiqueta)


@given(parsers.parse('que se abre el modal de asignación en la hoja "{hoja}"'))
def _abre_el_modal(contexto: Dict[str, Any], hoja: str) -> None:
    """
    Evalúa con Node el `staffToUse` real de `openVendorSelector` en `index.html`.

    El directorio de prueba y el evaluador viven en `test_lista_de_asignables`;
    aquí se reusan para no tener dos copias de la misma maquinaria.
    """
    import shutil

    from tests.test_lista_de_asignables import _del_modal

    if shutil.which("node") is None:
        pytest.skip("node no está instalado")

    contexto["ofrecidos"] = _del_modal(hoja)


@then("la lista ofrece solo a quien tiene tabla de cotizaciones")
def _ofrece_solo_vendedores(contexto: Dict[str, Any]) -> None:
    from tests.test_lista_de_asignables import DIRECTORIO

    con_tabla = [p["name"] for p in DIRECTORIO if p["sales"]]
    assert contexto["ofrecidos"] == con_tabla


@then("la lista ofrece a todo el directorio")
def _ofrece_a_todos(contexto: Dict[str, Any]) -> None:
    from tests.test_lista_de_asignables import DIRECTORIO

    assert contexto["ofrecidos"] == [p["name"] for p in DIRECTORIO]


@then("la actividad no se copia a ninguna otra tabla")
def _sin_copia(contexto: Dict[str, Any]) -> None:
    """
    Asignarse algo a uno mismo —con cualquiera de sus dos nombres— no produce
    copia. Si la produce, su tracker muestra la tarea duplicada, porque la vista
    une las dos hojas de la misma persona.
    """
    assert contexto["destinos"] == [], (
        f"es la misma persona: no hay a quién copiar, y se resolvió {contexto['destinos']}"
    )


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


@when(parsers.parse('{quien} resuelve el ticket con la nota "{nota}"'))
def _resuelve_con_nota(contexto: Dict[str, Any], quien: str, nota: str) -> None:
    _asegurar_ticket(contexto)
    contexto["ticket"] = contexto["tickets"].actualizar_estatus(
        contexto["ticket"].folio,
        TicketUpdate(estatus="RESUELTO", resolucion_notas=nota, resuelto_por=quien))


@then(parsers.parse('su aviso más reciente incluye la nota "{nota}"'))
def _aviso_reciente_con_nota(contexto: Dict[str, Any], nota: str) -> None:
    bandeja = contexto["tickets"].notificaciones.listar(contexto["reportante"])
    assert bandeja, "no hay ningún aviso en la bandeja"
    assert bandeja[0].nota == nota, (
        f"el aviso trae la nota {bandeja[0].nota!r} y se esperaba {nota!r}")


@then("su aviso más reciente no trae nota")
def _aviso_reciente_sin_nota(contexto: Dict[str, Any]) -> None:
    bandeja = contexto["tickets"].notificaciones.listar(contexto["reportante"])
    assert bandeja, "no hay ningún aviso en la bandeja"
    assert bandeja[0].nota is None, f"el aviso trae la nota {bandeja[0].nota!r}"


@then(parsers.parse('su aviso más reciente dice "{fragmento}"'))
def _aviso_reciente_dice(contexto: Dict[str, Any], fragmento: str) -> None:
    bandeja = contexto["tickets"].notificaciones.listar(contexto["reportante"])
    assert bandeja, "no hay ningún aviso en la bandeja"
    assert fragmento in bandeja[0].mensaje, (
        f"el aviso dice {bandeja[0].mensaje!r} y se esperaba que incluyera {fragmento!r}")


# ----------------------------------------------------------------------
# Calendario del dashboard
# ----------------------------------------------------------------------
#
# Quién ve qué: la fila sale en el calendario de quien la trabaja (RESPONSABLE
# o VENDEDOR), no en el de quien la repartió. El tracker se coloca por FECHA y
# las cotizaciones por F. INICIO.

def _tablas_del_calendario(contexto: Dict[str, Any]) -> Dict[str, list]:
    return contexto.setdefault("tablas_calendario", {})


def _apuntar(contexto: Dict[str, Any], hoja: str, fila: Dict[str, Any]) -> None:
    _tablas_del_calendario(contexto).setdefault(hoja, []).append(fila)


@given(parsers.parse('que "{persona}" tiene en su tabla la actividad "{concepto}" a cargo de "{quien}"'))
def _actividad_en_la_tabla(contexto: Dict[str, Any], persona: str, concepto: str, quien: str) -> None:
    _apuntar(contexto, asignacion_hoja(persona),
             {"FOLIO": f"AS-{len(_tablas_del_calendario(contexto)) + 1}",
              "CONCEPTO": concepto, "FECHA": "2026-08-10", "RESPONSABLE": quien})


@given(parsers.parse('que "{persona}" tiene en su tabla la actividad "{concepto}" sin responsable'))
def _actividad_sin_responsable(contexto: Dict[str, Any], persona: str, concepto: str) -> None:
    _apuntar(contexto, asignacion_hoja(persona),
             {"FOLIO": "AS-9", "CONCEPTO": concepto, "FECHA": "2026-08-10", "RESPONSABLE": ""})


@given(parsers.parse('que "{persona}" tiene en su tabla la actividad "{concepto}" con FECHA "{fecha}" a cargo de "{quien}"'))
def _actividad_con_fecha(contexto: Dict[str, Any], persona: str, concepto: str,
                         fecha: str, quien: str) -> None:
    _apuntar(contexto, asignacion_hoja(persona),
             {"FOLIO": "AS-8", "CONCEPTO": concepto, "FECHA": fecha, "RESPONSABLE": quien})


@given(parsers.parse('que "{persona}" tiene en su tabla de cotizaciones "{concepto}" con F. INICIO "{fecha}" a nombre de "{quien}"'))
def _cotizacion_con_f_inicio(contexto: Dict[str, Any], persona: str, concepto: str,
                             fecha: str, quien: str) -> None:
    from api.services.asignacion import tabla_de_cotizaciones

    _apuntar(contexto, tabla_de_cotizaciones(persona),
             {"FOLIO": "AV-7", "CONCEPTO": concepto, "F. VISITA": "2026-08-01",
              "F. INICIO": fecha, "F. ENTREGA": "2026-08-30", "VENDEDOR": quien})


def asignacion_hoja(persona: str) -> str:
    from api.services.asignacion import hoja_de_persona

    return hoja_de_persona(persona) or persona


@when(parsers.parse('"{persona}" abre su calendario'))
def _abre_su_calendario(contexto: Dict[str, Any], persona: str, monkeypatch) -> None:
    tablas = _tablas_del_calendario(contexto)
    monkeypatch.setattr(tracker_store, "read_rows",
                        lambda hoja: (list(tablas.get(hoja, [])), [], []))
    contexto["calendario"] = tracker_store.fetch_combined_calendar(persona)["data"]


@then(parsers.parse('el calendario muestra "{concepto}"'))
def _calendario_muestra(contexto: Dict[str, Any], concepto: str) -> None:
    conceptos = [f.get("CONCEPTO") for f in contexto["calendario"]]
    assert concepto in conceptos, f"el calendario muestra {conceptos}"


@then(parsers.parse('el calendario no muestra "{concepto}"'))
def _calendario_no_muestra(contexto: Dict[str, Any], concepto: str) -> None:
    conceptos = [f.get("CONCEPTO") for f in contexto["calendario"]]
    assert concepto not in conceptos, f"el calendario muestra {conceptos}"


@then(parsers.parse('el calendario muestra "{concepto}" con origen "{origen}" el día "{dia}"'))
def _calendario_muestra_con_origen(contexto: Dict[str, Any], concepto: str,
                                   origen: str, dia: str) -> None:
    filas = [f for f in contexto["calendario"] if f.get("CONCEPTO") == concepto]
    assert filas, f"el calendario no muestra {concepto}"
    assert filas[0]["ORIGEN"] == origen
    assert filas[0]["FECHA_CALENDARIO"] == dia


# ----------------------------------------------------------------------
# Banco de Cotizaciones
# ----------------------------------------------------------------------
#
# El periodo lo decide F. INICIO, la misma regla del calendario, y una
# cotización repartida entre dos tablas es una sola cotización en el banco.

BANCO_HEADERS = ["FOLIO", "AREA", "CLIENTE", "CONCEPTO", "VENDEDOR", "F. INICIO",
                 "ESTATUS", "FECHA"]


def _tablas_del_banco(contexto: Dict[str, Any]) -> Dict[str, list]:
    return contexto.setdefault("tablas_banco", {})


@given(parsers.parse('que "{cliente}" tiene la cotización "{folio}" con F. INICIO "{fecha}" en "{hoja}"'))
def _cotizacion_en_el_banco(contexto: Dict[str, Any], cliente: str, folio: str,
                            fecha: str, hoja: str) -> None:
    _tablas_del_banco(contexto).setdefault(hoja, []).append(
        [folio, "CONSTRUCCION", cliente, "COTIZAR NAVE", "RAMIRO RODRIGUEZ",
         # La columna FECHA lleva a propósito otro mes: si el banco la usara
         # para agrupar —el defecto que se arregló— el escenario fallaría.
         fecha, "ASIGNADO", "2026-09-15"])


@when(parsers.parse('se abre el banco de "{mes}" de "{anio}"'))
def _abre_el_banco(contexto: Dict[str, Any], mes: str, anio: str, monkeypatch) -> None:
    from api.services import sheets

    tablas = _tablas_del_banco(contexto)
    monkeypatch.setattr(tracker_store, "read_values",
                        lambda hoja: ([BANCO_HEADERS] + tablas[hoja]) if hoja in tablas else [])
    monkeypatch.setattr(sheets, "hojas_de_cotizaciones", lambda: list(tablas))
    contexto["banco"] = tracker_store.fetch_info_bank_companies(anio, mes)["data"]


@then(parsers.parse('el banco muestra al cliente "{cliente}"'))
def _banco_muestra_cliente(contexto: Dict[str, Any], cliente: str) -> None:
    nombres = [c["name"] for c in contexto["banco"]]
    assert cliente in nombres, f"el banco muestra {nombres}"


@then(parsers.parse('el banco no muestra al cliente "{cliente}"'))
def _banco_no_muestra_cliente(contexto: Dict[str, Any], cliente: str) -> None:
    nombres = [c["name"] for c in contexto["banco"]]
    assert cliente not in nombres, f"el banco muestra {nombres}"


@then(parsers.parse('el banco cuenta {total:d} cotización para el cliente "{cliente}"'))
def _banco_cuenta_cotizaciones(contexto: Dict[str, Any], total: int, cliente: str) -> None:
    tarjetas = [c for c in contexto["banco"] if c["name"] == cliente]
    assert tarjetas, f"el banco no muestra a {cliente}"
    assert tarjetas[0]["count"] == total


# ----------------------------------------------------------------------
# Control de alta — el candado es del Tracker
# ----------------------------------------------------------------------

@given(parsers.parse(
    'que llega la actividad nueva "{concepto}" sin PRIORIDAD, RIESGOS ni FEC. EST. FIN'))
def _alta_sin_los_tres(contexto: Dict[str, Any], concepto: str) -> None:
    contexto["alta"] = {"CONCEPTO": concepto, "RESPONSABLE": "JAIME OLIVO",
                        "CLIENTE": "NEMAK", "_tempId": f"tmp-bdd-{concepto}"}


@given(parsers.parse(
    'que llega la actividad nueva "{concepto}" con PRIORIDAD "{prioridad}", '
    'RIESGOS "{riesgos}" y FEC. EST. FIN "{fecha}"'))
def _alta_completa(contexto: Dict[str, Any], concepto: str, prioridad: str,
                   riesgos: str, fecha: str) -> None:
    contexto["alta"] = {"CONCEPTO": concepto, "RESPONSABLE": "JAIME OLIVO",
                        "PRIORIDAD": prioridad, "RIESGOS": riesgos,
                        "FEC. EST. FIN": fecha, "_tempId": f"tmp-bdd-{concepto}"}


@given(parsers.parse(
    'que la hoja "{hoja}" trae las columnas PRIORIDAD, RIESGOS y FEC. EST. FIN'))
def _hoja_con_las_tres_columnas(contexto: Dict[str, Any], hoja: str) -> None:
    contexto["columnas_extra"] = ["PRIORIDAD", "RIESGOS", "FEC. EST. FIN"]


@when(parsers.parse('se intenta dar de alta en la hoja "{hoja}"'))
def _intenta_dar_de_alta(contexto: Dict[str, Any], hoja: str,
                         monkeypatch: pytest.MonkeyPatch) -> None:
    contexto["motor"] = MemoryEngine({
        "tasks": [], "quotes": [], "people": [], "plan_semanal": [],
        "task_involucrados": [], "system_log": [],
    })
    base = (list(tracker_store.ENCABEZADOS_VENTAS) if is_sales_sheet(hoja)
            else list(tracker_store.ENCABEZADOS_TAREA))
    cabecera = base + list(contexto.get("columnas_extra", []))
    monkeypatch.setattr(tracker_store, "_persistencia",
                        lambda: PersistenciaTracker(contexto["motor"]))
    monkeypatch.setattr(tracker_store, "read_values", lambda _hoja: [cabecera])
    contexto["respuesta"] = tracker_store.save_tracker_batch(
        hoja, [dict(contexto["alta"])],
        username="ANTONIA_VENTAS" if is_sales_sheet(hoja) else "JAIME_OLIVO",
    )
    contexto["tabla"] = "quotes" if is_sales_sheet(hoja) else "tasks"


@then("el alta se rechaza nombrando PRIORIDAD, RIESGOS y FEC. EST. FIN")
def _alta_rechazada(contexto: Dict[str, Any]) -> None:
    respuesta = contexto["respuesta"]
    assert respuesta["success"] is False, respuesta
    for campo in ("PRIORIDAD", "RIESGOS", "FEC. EST. FIN"):
        assert campo in respuesta["message"], respuesta["message"]


@then("no se escribe ninguna fila")
def _sin_escribir(contexto: Dict[str, Any]) -> None:
    concepto = contexto["alta"]["CONCEPTO"]
    filas = [f for f in contexto["motor"].select(contexto["tabla"])
             if f.get("concepto") == concepto]
    assert filas == [], "el rechazo tiene que ocurrir antes de escribir"


@then("el alta se acepta")
def _alta_aceptada(contexto: Dict[str, Any]) -> None:
    respuesta = contexto["respuesta"]
    assert respuesta["success"] is True, respuesta.get("message")
    concepto = contexto["alta"]["CONCEPTO"]
    filas = [f for f in contexto["motor"].select(contexto["tabla"])
             if f.get("concepto") == concepto]
    assert len(filas) == 1, f"se esperaba 1 fila de {concepto}, hay {len(filas)}"


# ----------------------------------------------------------------------
# Prospección geoespacial — solo se ofrece a quien se puede contactar
# ----------------------------------------------------------------------
#
# Estos pasos construyen un directorio de verdad —un SQLite con el mismo
# esquema que el artefacto que viaja en el bundle— y lo consultan con el
# servicio real. Nada de dobles: lo que el escenario aprueba es la regla que
# corre en producción, no una reimplementación suya.

_ESQUEMA_DENUE = """
CREATE TABLE denue (
  id TEXT PRIMARY KEY, nom_estab TEXT, nombre_act TEXT, codigo_act TEXT,
  per_ocu TEXT, telefono TEXT, correoelec TEXT, www TEXT,
  municipio TEXT, nom_vial TEXT, numero_ext TEXT, cod_postal TEXT,
  latitud REAL, longitud REAL
);
"""


def _celda(valor: str) -> Optional[str]:
    """Una casilla en blanco de la tabla es "no lo declaró", que es NULL."""
    limpio = str(valor).strip()
    return limpio or None


@given("el directorio de negocios:")
def _directorio_de_negocios(contexto: Dict[str, Any], datatable: List[List[str]],
                            tmp_path) -> None:
    import sqlite3

    encabezados, *filas = datatable
    columna = {nombre: encabezados.index(nombre) for nombre in encabezados}

    ruta = tmp_path / "directorio.sqlite"
    conexion = sqlite3.connect(ruta)
    with conexion:
        conexion.executescript(_ESQUEMA_DENUE)
        for numero, fila in enumerate(filas, start=1):
            conexion.execute(
                "INSERT INTO denue VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
                (
                    f"{numero:02d}",
                    fila[columna["nombre"]].strip(),
                    "Comercio al por menor en ferreterías y tlapalerías", "467111",
                    fila[columna["personal"]].strip(),
                    _celda(fila[columna["telefono"]]),
                    _celda(fila[columna["correo"]]),
                    _celda(fila[columna["pagina"]]),
                    "Cuauhtémoc", "REPUBLICA DE CUBA", "10", "06010",
                    19.44, -99.14,
                ),
            )
    conexion.close()
    contexto["directorio"] = RepositorioDenue(ruta)


@when("Compras pide la lista de prospectos")
def _lista_de_prospectos(contexto: Dict[str, Any]) -> None:
    contexto["lista"] = prospeccion.establecimientos(
        contexto["directorio"], solo_con_contacto=True)


@when("Compras pide la lista de prospectos de 11 o más personas")
def _lista_de_prospectos_grandes(contexto: Dict[str, Any]) -> None:
    contexto["lista"] = prospeccion.establecimientos(
        contexto["directorio"], solo_con_contacto=True, personal_min=11)


@when("se consulta el directorio completo")
def _directorio_completo(contexto: Dict[str, Any]) -> None:
    contexto["lista"] = prospeccion.establecimientos(
        contexto["directorio"], solo_con_contacto=False)


@then(parsers.parse("la lista trae {cantidad:d} negocios"))
def _la_lista_trae(contexto: Dict[str, Any], cantidad: int) -> None:
    assert contexto["lista"]["total"] == cantidad
    assert len(contexto["lista"]["items"]) == cantidad


@then(parsers.parse('"{nombre}" aparece en la lista'))
def _aparece_en_la_lista(contexto: Dict[str, Any], nombre: str) -> None:
    assert nombre in {fila["nom_estab"] for fila in contexto["lista"]["items"]}


@then(parsers.parse('"{nombre}" no aparece en la lista'))
def _no_aparece_en_la_lista(contexto: Dict[str, Any], nombre: str) -> None:
    assert nombre not in {fila["nom_estab"] for fila in contexto["lista"]["items"]}

# ----------------------------------------------------------------------
# Prospección geoespacial — el recorrido del prospecto por el embudo
# ----------------------------------------------------------------------
#
# Contra el repositorio real sobre `MemoryEngine`. R7: ninguna prueba escribe en
# la base de producción, y el doble reproduce lo que aquí importa —el upsert que
# fusiona— en vez de fingirlo.

@given(parsers.parse('el negocio "{nombre}" del mapa, sin marcar'))
def _negocio_sin_marcar(contexto: Dict[str, Any], nombre: str) -> None:
    contexto["negocio"] = nombre
    # El identificador que trae el catálogo del INEGI para ese establecimiento.
    contexto["denue_id"] = "9274655"
    contexto["prospectos"] = GeoProspectoRepository(MemoryEngine())


@when(parsers.parse('Compras lo marca como "{estado}"'))
def _compras_lo_marca(contexto: Dict[str, Any], estado: str) -> None:
    guardado = contexto["prospectos"].guardar(
        ProspectoWrite(establecimiento_id=contexto["denue_id"], estado=estado))
    contexto.setdefault("historial", []).append(guardado)


@when(parsers.parse(
    'Compras lo marca como "{estado}" a nombre de "{vendedor}" con la nota "{nota}"'))
def _compras_lo_marca_con_dueno(contexto: Dict[str, Any], estado: str,
                                vendedor: str, nota: str) -> None:
    contexto.setdefault("historial", []).append(
        contexto["prospectos"].guardar(ProspectoWrite(
            establecimiento_id=contexto["denue_id"], estado=estado,
            vendedor=vendedor, nota=nota)))


@when(parsers.parse('Compras intenta marcarlo como "{estado}"'))
def _compras_intenta_marcarlo(contexto: Dict[str, Any], estado: str) -> None:
    try:
        contexto["prospectos"].guardar(
            ProspectoWrite(establecimiento_id=contexto["denue_id"], estado=estado))
        contexto["rechazo"] = None
    except ValidationError as error:
        contexto["rechazo"] = error


@then(parsers.parse('el negocio queda en "{estado}"'))
def _el_negocio_queda_en(contexto: Dict[str, Any], estado: str) -> None:
    assert contexto["prospectos"].obtener(contexto["denue_id"]).estado == estado


@then("queda registrado el día en que entró al embudo")
def _queda_registrada_la_entrada(contexto: Dict[str, Any]) -> None:
    assert contexto["prospectos"].obtener(contexto["denue_id"]).created_at is not None


@then("el día en que entró al embudo es el mismo del principio")
def _la_entrada_no_se_movio(contexto: Dict[str, Any]) -> None:
    fechas = {p.created_at for p in contexto["historial"]}
    assert len(fechas) == 1, f"la fecha de entrada cambió por el camino: {fechas}"


@then("hay un solo registro de ese negocio")
def _un_solo_registro(contexto: Dict[str, Any]) -> None:
    assert len(contexto["prospectos"].engine.select(TABLA_PROSPECTOS)) == 1


@then(parsers.parse('el negocio lo lleva "{vendedor}"'))
def _lo_lleva(contexto: Dict[str, Any], vendedor: str) -> None:
    assert contexto["prospectos"].obtener(contexto["denue_id"]).vendedor == vendedor


@then(parsers.parse('la nota del negocio dice "{nota}"'))
def _la_nota_dice(contexto: Dict[str, Any], nota: str) -> None:
    assert contexto["prospectos"].obtener(contexto["denue_id"]).nota == nota


@then("el sistema rechaza el momento desconocido")
def _rechaza_el_momento(contexto: Dict[str, Any]) -> None:
    assert contexto["rechazo"] is not None
    assert "estado debe ser uno de" in str(contexto["rechazo"])


@then("el negocio sigue sin marcar")
def _sigue_sin_marcar(contexto: Dict[str, Any]) -> None:
    """
    Lo que se protege es que un momento inventado no deje al negocio en `NUEVO`:
    eso diría que nadie lo ha contactado, borrando trabajo que alguien ya hizo.
    """
    with pytest.raises(ProspectoNoEncontrado):
        contexto["prospectos"].obtener(contexto["denue_id"])


# ----------------------------------------------------------------------
# Agente de Consultas: la lista blanca de destinatarios y el guardarrail SQL
# ----------------------------------------------------------------------
# `tests/test_agente_sql.py` prueba lo mismo por unidad. Estos escenarios
# existen porque son las dos reglas del modulo que una persona que no programa
# tiene que poder leer y aprobar: a quien se le puede escribir, y que el agente
# no escriba en la base.


@given(parsers.parse('que el directorio de la empresa incluye "{direccion}"'))
def _directorio_incluye(contexto: Dict[str, Any], direccion: str, monkeypatch) -> None:
    monkeypatch.delenv(agente_correo.ENV_DESTINATARIOS, raising=False)
    monkeypatch.setenv("SMTP_HOST", "smtp.ejemplo.com")
    assert direccion in agente_correo.destinatarios_permitidos()

    contexto["correos_enviados"] = []
    monkeypatch.setattr(
        "api.services.correo.enviar",
        lambda **kw: contexto["correos_enviados"].append(kw) or {"success": True},
    )


@given("que el servidor de correo no está configurado")
def _sin_servidor_de_correo(monkeypatch) -> None:
    monkeypatch.delenv("SMTP_HOST", raising=False)


@given(parsers.parse('un borrador aprobado para el área "{area}"'))
def _borrador_aprobado(contexto: Dict[str, Any], area: str) -> None:
    contexto["borradores"] = {
        area: {"asunto": f"Reporte de {area}", "cuerpo": "Cuerpo revisado por una persona."}
    }
    contexto["area"] = area


@when(parsers.parse('se intenta mandarlo a "{destino}"'))
def _mandar_a(contexto: Dict[str, Any], destino: str) -> None:
    contexto["envio"] = agente_correo.enviar(
        contexto["borradores"], {contexto["area"]: destino})


@when(parsers.parse('se intenta mandarlo a "{destino}" con copia a "{copia}"'))
def _mandar_con_copia(contexto: Dict[str, Any], destino: str, copia: str) -> None:
    contexto["envio"] = agente_correo.enviar(
        contexto["borradores"], {contexto["area"]: destino}, copia=[copia])


@then("no se manda ningún correo")
def _no_se_manda_nada(contexto: Dict[str, Any]) -> None:
    assert contexto["envio"]["success"] is False
    assert contexto["correos_enviados"] == []


@then(parsers.parse("se manda {cantidad:d} correo"))
def _se_mandan_correos(contexto: Dict[str, Any], cantidad: int) -> None:
    assert contexto["envio"]["success"] is True
    assert len(contexto["correos_enviados"]) == cantidad


@then(parsers.parse('el correo llega a "{destino}"'))
def _el_correo_llega_a(contexto: Dict[str, Any], destino: str) -> None:
    assert contexto["correos_enviados"][0]["destinatarios"] == [destino]


@then(parsers.parse('el motivo menciona "{fragmento}"'))
def _el_motivo_menciona(contexto: Dict[str, Any], fragmento: str) -> None:
    """
    Que el motivo NOMBRE la direccion rechazada es la mitad de la regla: sin
    eso, quien pulso enviar sabe que algo fallo pero no cual de los correos.
    """
    assert fragmento in contexto["envio"]["message"]


@given("que el agente consulta la tabla de actividades")
def _agente_sobre_actividades(contexto: Dict[str, Any]) -> None:
    contexto["esquema"] = agente_esquemas.ESQUEMAS["tasks"]
    contexto["sql_ejecutado"] = []


@when(parsers.parse('el modelo propone la consulta "{consulta}"'))
def _el_modelo_propone(contexto: Dict[str, Any], consulta: str) -> None:
    estado = {"sql": consulta, "intentos": 1}
    contexto["resultado_nodo"] = agente_sql.nodo_ejecutar_sql(
        estado,
        lambda sql: contexto["sql_ejecutado"].append(sql) or [],
        contexto["esquema"],
    )


@then("la consulta se rechaza antes de tocar la base")
def _rechazada_antes_de_tocar_la_base(contexto: Dict[str, Any]) -> None:
    assert "BLOQUEO" in contexto["resultado_nodo"]["error"]
    assert contexto["sql_ejecutado"] == []


@then("la consulta se ejecuta contra la base")
def _se_ejecuta(contexto: Dict[str, Any]) -> None:
    assert contexto["resultado_nodo"]["error"] == ""
    assert len(contexto["sql_ejecutado"]) == 1


@then("la consulta que llega a la base trae un límite de filas")
def _trae_limite(contexto: Dict[str, Any]) -> None:
    assert contexto["sql_ejecutado"][0].rstrip().endswith(str(agente_sql.TECHO_FILAS))


# ----------------------------------------------------------------------
# Lo que capturo se guarda en la fila que yo veo (BUG-0015)
# ----------------------------------------------------------------------

@given(parsers.parse('que "{quien}" le asignó a "{persona}" la actividad "{folio}"'))
def _actividad_asignada(contexto: Dict[str, Any], quien: str, persona: str,
                        folio: str) -> None:
    """
    Las dos filas de la misma actividad: la de quien asignó, con la clave global
    del folio, y la copia de quien la recibió, con clave propia por hoja.
    """
    concepto = "REUNION CON EL ING GERARDO BENITO"
    contexto["folio"] = folio
    contexto["persona"] = persona
    contexto["concepto"] = concepto
    contexto["motor"] = MemoryEngine({
        "tasks": [
            {"id": "11111111-1111-1111-1111-111111111111", "dedupe_key": folio,
             "folio": folio, "source_sheet": quien, "concepto": concepto,
             "assignee_raw": persona, "avance": 0.0, "status": "ASIGNADO",
             "restricciones": ""},
            {"id": "22222222-2222-2222-2222-222222222222",
             "dedupe_key": f"{persona}::{folio}", "folio": folio,
             "source_sheet": persona, "concepto": concepto,
             "assignee_raw": persona, "avance": 0.0, "status": "ASIGNADO",
             "restricciones": ""},
        ],
        "quotes": [], "people": [], "plan_semanal": [],
        "task_involucrados": [], "system_log": [],
    })


@when(parsers.parse(
    '"{persona}" le pone {avance:d} % de avance y la restricción "{restriccion}"'))
def _captura_avance_y_restriccion(contexto: Dict[str, Any], persona: str,
                                  avance: int, restriccion: str,
                                  monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(tracker_store, "_persistencia",
                        lambda: PersistenciaTracker(contexto["motor"]))
    monkeypatch.setattr(tracker_store, "read_values",
                        lambda hoja: [["FOLIO", "CONCEPTO", "AVANCE %",
                                       "RESTRICCIONES", "STATUS"]])
    contexto["respuesta"] = tracker_store.save_tracker_batch(
        persona,
        [{"FOLIO": contexto["folio"], "CONCEPTO": contexto["concepto"],
          "AVANCE %": avance, "RESTRICCIONES": restriccion, "STATUS": "ASIGNADO"}],
        username=persona.replace(" ", "_"),
    )


def _fila_de(contexto: Dict[str, Any], hoja: str) -> Dict[str, Any]:
    filas = [f for f in contexto["motor"].select("tasks")
             if f.get("source_sheet") == hoja and f.get("folio") == contexto["folio"]]
    assert filas, f"no hay fila de {contexto['folio']} en la hoja {hoja!r}"
    return filas[0]


@then(parsers.parse('su tracker muestra {avance:d} % de avance en "{folio}"'))
def _su_tracker_muestra_el_avance(contexto: Dict[str, Any], avance: int,
                                  folio: str) -> None:
    assert contexto["respuesta"]["success"] is True, contexto["respuesta"].get("message")
    fila = _fila_de(contexto, contexto["persona"])
    assert float(fila["avance"]) == float(avance)


@then(parsers.parse('su tracker muestra la restricción "{restriccion}"'))
def _su_tracker_muestra_la_restriccion(contexto: Dict[str, Any],
                                       restriccion: str) -> None:
    assert _fila_de(contexto, contexto["persona"])["restricciones"] == restriccion


@then(parsers.parse('la fila de "{hoja}" conserva su restricción vacía'))
def _la_otra_fila_no_se_toca(contexto: Dict[str, Any], hoja: str) -> None:
    assert _fila_de(contexto, hoja)["restricciones"] == ""


@then(parsers.parse('existen {cuantas:d} filas con el folio "{folio}"'))
def _cuantas_filas_con_el_folio(contexto: Dict[str, Any], cuantas: int,
                                folio: str) -> None:
    filas = [f for f in contexto["motor"].select("tasks") if f.get("folio") == folio]
    assert len(filas) == cuantas, [f["dedupe_key"] for f in filas]
