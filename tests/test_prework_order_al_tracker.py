"""
La Pre Work Order aterriza en el Tracker: una tarea por línea de programa.

Qué estaba mal y por qué existe este archivo
--------------------------------------------
La Pre Work Order ya escribía en el Tracker, pero con dos defectos medidos:

1. **Sin clasificación utilizable.** `process_and_save_work_order` ponía
   `CLASIFICACION = "Media"` por defecto (el formulario nunca mandaba el campo).
   El Tracker clasifica en `A` / `AA` / `AAA` —son las claves de `SLA_LIMITS`— y
   `traffic_light_color` devuelve `None` para cualquier otra cosa: **toda** tarea
   nacida de una Pre Work Order entraba al tracker sin semáforo y sin SLA. Lo
   que sí viajaba era `PRIORIDAD` ("AAA - Alta Prioridad"), que es otra columna
   y no alimenta el semáforo.

2. **El programa se quedaba inerte.** Cada línea de `wo_programa` trae
   responsable, fechas y estatus propios —tiene la forma de una tarea— pero al
   Tracker solo iba **una** fila global de la orden completa, con
   `INVOLUCRADOS` = quien elaboró el formulario, no quien ejecuta el trabajo.

El reparto por línea sigue el camino que la papa caliente ya dejó probado
(`docs/FLUJO_PAPA_CALIENTE.md`): destino `resolve_worker_sheet`, copia con clave
propia por hoja, y nunca una tabla de ventas.

La marca de sección es `[PWO: <SECCION>]` y no `[<SECCION>]` a propósito: ver
`test_una_linea_de_programa_no_es_una_fase_de_papa_caliente`.
"""

from __future__ import annotations

import os
import re
import sys
from typing import Any, Dict, List

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from api.services import asignacion  # noqa: E402
from api.services import tracker_rules as rules  # noqa: E402
from api.services import work_order  # noqa: E402
from backend.core.engines.memoria import MemoryEngine  # noqa: E402
from backend.services.persistencia import PersistenciaTracker  # noqa: E402

FOLIO = "1001AC Electro 060826"

CABECERA = {
    "FOLIO": FOLIO,
    "AREA": "ELECTROMECANICA",
    "CLASIFICACION": "AA",
    "FECHA": "06/08/26",
    "CLIENTE": "ACME CORP",
}


def _linea(**campos: Any) -> Dict[str, Any]:
    """Una línea de programa como la manda el formulario."""
    base = {
        "description": "MONTAR TABLERO",
        "seccion": "TRABAJO",
        "responsable": "TERESA GARZA",
        "fechaEntrega": "20/08/26",
    }
    base.update(campos)
    return base


# ----------------------------------------------------------------------
# 1. La clasificación: el campo que faltaba
# ----------------------------------------------------------------------

@pytest.mark.parametrize("clase", ["A", "AA", "AAA"])
def test_las_tres_clasificaciones_del_tracker_se_aceptan(clase):
    assert work_order.clasificacion_de_tracker(clase) == clase


@pytest.mark.parametrize("entrada,esperado", [
    ("aa", "AA"), ("  AAA  ", "AAA"), ("a", "A"),
])
def test_la_clasificacion_se_normaliza(entrada, esperado):
    """El formulario manda lo que el usuario eligió; el espacio y la caja sobran."""
    assert work_order.clasificacion_de_tracker(entrada) == esperado


@pytest.mark.parametrize("invalida", ["Media", "ALTA", "", None, "B", "AAAA"])
def test_lo_que_el_semaforo_no_entiende_no_pasa_por_clasificacion(invalida):
    """
    `"Media"` es justo el valor que ponía el default y el que rompía el semáforo.

    La función no inventa una clase: devuelve `""` y quien llama decide. Para la
    Pre Work Order, decidir es rechazar la orden (prueba de abajo).
    """
    assert work_order.clasificacion_de_tracker(invalida) == ""


@pytest.mark.parametrize("clase", ["A", "AA", "AAA"])
def test_toda_clasificacion_aceptada_enciende_el_semaforo(clase):
    """
    El contrato de fondo: lo que esta función deja pasar, `traffic_light_color`
    lo tiene que saber pintar. Es la comprobación que ata las dos mitades y la
    que fallaba con `"Media"`.
    """
    assert rules.traffic_light_color(clase, 0) is not None


def test_el_semaforo_no_sabe_pintar_el_default_viejo():
    """La regresión, dicha al derecho: por esto se cambió el default."""
    assert rules.traffic_light_color("Media", 0) is None


# ----------------------------------------------------------------------
# 2. El reparto por línea de programa
# ----------------------------------------------------------------------

def test_cada_linea_con_responsable_genera_una_tarea_en_su_tracker():
    derivadas = work_order.tareas_de_programa([
        _linea(description="MONTAR TABLERO", responsable="TERESA GARZA"),
        _linea(description="CABLEAR CHAROLA", responsable="ANGEL SALINAS"),
    ], CABECERA)

    assert [hoja for hoja, _ in derivadas] == ["TERESA GARZA", "ANGEL SALINAS"]


def test_la_linea_hereda_la_cabecera_y_aporta_lo_suyo():
    (_, fila), = work_order.tareas_de_programa([
        _linea(description="MONTAR TABLERO", seccion="TRABAJO",
               fechaEntrega="20/08/26")
    ], CABECERA)

    # De la cabecera: el folio ancla la línea a su Pre Work Order.
    assert fila["FOLIO"] == FOLIO
    assert fila["AREA"] == "ELECTROMECANICA"
    assert fila["CLASIFICACION"] == "AA"
    # De la línea:
    assert fila["CONCEPTO"] == "MONTAR TABLERO [PWO: TRABAJO]"
    assert fila["INVOLUCRADOS"] == "TERESA GARZA"
    assert fila["FECHA_RESPUESTA"] == "20/08/26"
    # Nace igual que una fase delegada: asignada y sin avance.
    assert fila["ESTATUS"] == "ASIGNADO"
    assert fila["AVANCE"] == ""


def test_una_linea_con_varios_responsables_da_una_tarea_a_cada_uno():
    """
    El formulario deja elegir varias personas por línea (`RESPONSABLE` se guarda
    con `join(', ')`). Cada una necesita su fila: una tarea que vive en la hoja
    de otro no la ve nadie.
    """
    derivadas = work_order.tareas_de_programa(
        [_linea(responsable=["TERESA GARZA", "ANGEL SALINAS"])], CABECERA)

    assert sorted(hoja for hoja, _ in derivadas) == ["ANGEL SALINAS", "TERESA GARZA"]
    for _, fila in derivadas:
        assert fila["INVOLUCRADOS"] in {"TERESA GARZA", "ANGEL SALINAS"}


def test_el_responsable_en_una_cadena_con_comas_se_reparte_igual():
    derivadas = work_order.tareas_de_programa(
        [_linea(responsable="TERESA GARZA, ANGEL SALINAS")], CABECERA)

    assert sorted(hoja for hoja, _ in derivadas) == ["ANGEL SALINAS", "TERESA GARZA"]


@pytest.mark.parametrize("sin_dueno", ["", "   ", None, []])
def test_una_linea_sin_responsable_no_genera_tarea(sin_dueno):
    """
    Decisión explícita: no se le asigna al cotizador por descarte.

    Inventar un dueño es peor que no crear la tarea — la línea sigue viva en
    `wo_programa`, que es su sitio, y nadie recibe trabajo que no aceptó.
    """
    assert work_order.tareas_de_programa([_linea(responsable=sin_dueno)], CABECERA) == []


@pytest.mark.parametrize("vacia", ["", "   ", None])
def test_una_linea_sin_descripcion_no_genera_tarea(vacia):
    """
    El formulario precrea renglones en blanco en las cuatro secciones del
    programa. Sin este filtro, cada Pre Work Order sembraría tareas fantasma con
    solo la marca de sección por concepto.
    """
    assert work_order.tareas_de_programa([_linea(description=vacia)], CABECERA) == []


def test_una_linea_sin_seccion_no_pierde_su_concepto():
    """Sin sección no hay marca, pero la tarea se crea: el trabajo existe igual."""
    (_, fila), = work_order.tareas_de_programa(
        [_linea(description="MONTAR TABLERO", seccion="")], CABECERA)

    assert fila["CONCEPTO"] == "MONTAR TABLERO"


# ----------------------------------------------------------------------
# 3. Las dos reglas que no se pueden pisar
# ----------------------------------------------------------------------

@pytest.mark.parametrize("vendedor", asignacion.VENDEDORES_CON_TABLA)
def test_una_linea_de_programa_nunca_cae_en_una_tabla_de_ventas(vendedor):
    """
    La imagen simétrica de la regla de la papa caliente (AGENTS.md §3): una
    línea de trabajo es trabajo, no una venta, aunque su responsable venda.
    """
    (hoja, _), = work_order.tareas_de_programa(
        [_linea(responsable=vendedor)], CABECERA)

    assert not rules.is_sales_sheet(hoja), (
        f"{vendedor}: una línea de programa se filtró a su tabla de ventas")


def test_el_trabajo_de_antonia_va_a_su_tracker_personal():
    """La Ley de Antonia: `ANTONIA_VENTAS` es una tabla, no una persona."""
    (hoja, _), = work_order.tareas_de_programa(
        [_linea(responsable="ANTONIA_VENTAS")], CABECERA)

    assert hoja == rules.ANTONIA_PERSONAL_SHEET


@pytest.mark.parametrize("seccion", ["VISITA", "REQUERIMIENTO", "PRECONSTRUCCION", "TRABAJO"])
def test_una_linea_de_programa_no_es_una_fase_de_papa_caliente(seccion):
    """
    La colisión que hay que evitar, y el motivo del prefijo `PWO:`.

    `es_delegacion_de_fase` responde por la marca entre corchetes del CONCEPTO.
    Si una sección del programa normalizara a un paso de `PROCESS_STEPS`, las
    tres puertas que separan la papa caliente de la asignación normal
    (`destinos_espejo`, el reverse sync y el bloqueo de fase) empezarían a tratar
    una línea de Pre Work Order como si fuera una fase de cotización — y el
    reverse sync le devolvería `PROCESO_LOG` a una cotización que no existe.
    """
    (_, fila), = work_order.tareas_de_programa(
        [_linea(seccion=seccion)], CABECERA)

    assert asignacion.es_delegacion_de_fase(fila) is False
    assert rules.extract_phase_from_concepto(fila["CONCEPTO"]) == ""


def test_la_marca_de_seccion_sobrevive_a_una_descripcion_con_corchetes():
    """
    Una descripción puede traer corchetes propios ("REVISAR TABLERO [L]"), y
    `extract_phase_from_concepto` lee **todas** las marcas, no solo la última.
    Este es el caso que de verdad podría confundirse con la fase `L`
    (Levantamiento), así que se fija: el saneado va sobre la descripción.
    """
    (_, fila), = work_order.tareas_de_programa(
        [_linea(description="REVISAR TABLERO [L]")], CABECERA)

    assert asignacion.es_delegacion_de_fase(fila) is False


# ----------------------------------------------------------------------
# 4. De punta a punta contra la base
# ----------------------------------------------------------------------

def _motor() -> MemoryEngine:
    return MemoryEngine({
        "quotes": [], "tasks": [], "people": [], "plan_semanal": [],
        "task_involucrados": [], "system_log": [], "work_orders": [],
        "wo_programa": [],
    })


@pytest.fixture
def base(monkeypatch):
    motor = _motor()
    monkeypatch.setattr(work_order, "_persistencia", lambda: PersistenciaTracker(motor))
    monkeypatch.setattr(work_order, "_engine", lambda: motor)
    monkeypatch.setattr(work_order, "save_to_obsidian", lambda *a, **k: None)
    monkeypatch.setattr(work_order, "get_next_sequence", lambda *a, **k: "1001")
    return motor


def _orden(**campos: Any) -> Dict[str, Any]:
    base = {
        "cliente": "ACME CORP",
        "especialidad": "ELECTROMECANICA",
        "concepto": "LEVANTAMIENTO DE NAVE",
        "clasificacion": "AA",
        "responsable": "ADMINISTRADOR",
        "programa": [
            _linea(description="MONTAR TABLERO", responsable="TERESA GARZA"),
            _linea(description="CABLEAR CHAROLA", responsable="ANGEL SALINAS",
                   seccion="PRECONSTRUCCION"),
        ],
    }
    base.update(campos)
    return base


def _tareas_de(motor: MemoryEngine, hoja: str) -> List[Dict[str, Any]]:
    return [f for f in motor.select("tasks") if f.get("source_sheet") == hoja]


def test_guardar_una_pwo_siembra_el_tracker_de_cada_responsable(base):
    respuesta = work_order.process_and_save_work_order([_orden()], "PREWORK_ORDER")

    assert respuesta["success"] is True, respuesta.get("message")
    assert _tareas_de(base, "TERESA GARZA"), "Teresa no recibió su línea de programa"
    assert _tareas_de(base, "ANGEL SALINAS"), "Ángel no recibió su línea de programa"


def test_la_tarea_derivada_conserva_el_folio_de_su_orden(base):
    respuesta = work_order.process_and_save_work_order([_orden()], "PREWORK_ORDER")
    folio = respuesta["ids"][0]

    (tarea,) = _tareas_de(base, "TERESA GARZA")
    assert tarea["folio"] == folio, (
        "La línea no queda anclada a su Pre Work Order: sin el folio no hay "
        "forma de volver del Tracker al levantamiento")


def test_una_pwo_sin_clasificacion_valida_no_se_guarda(base):
    """
    Se rechaza **antes** de escribir nada: una orden a medias en el tracker es
    peor que una orden rechazada, porque nadie la vuelve a mirar.
    """
    respuesta = work_order.process_and_save_work_order(
        [_orden(clasificacion="Media")], "PREWORK_ORDER")

    assert respuesta["success"] is False
    assert "clasificacion" in respuesta["message"].lower()
    assert base.select("tasks") == []
    assert base.select("work_orders") == []


def test_el_ppc_dinamico_sigue_guardando_como_antes(base):
    """
    `process_and_save_work_order` sirve a tres caminos: la Pre Work Order, el
    PPC dinámico y el lote de actividades. La validación estricta es solo del
    primero; los otros dos no se tocan.
    """
    respuesta = work_order.process_and_save_work_order([{
        "especialidad": "MANTENIMIENTO",
        "concepto": "REVISAR BOMBA",
        "responsable": "TERESA GARZA",
    }], "ADMINISTRADOR")

    assert respuesta["success"] is True, respuesta.get("message")


# ----------------------------------------------------------------------
# 5. El formulario, que es donde nace la clasificación
# ----------------------------------------------------------------------

RAIZ = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


@pytest.fixture(scope="module")
def indice() -> str:
    with open(os.path.join(RAIZ, "index.html"), "r", encoding="utf-8") as f:
        return f.read()


def test_el_formulario_tiene_selector_de_clasificacion(indice):
    """
    Sin el campo, la validación del backend rechaza toda Pre Work Order y la
    cuenta PREWORK_ORDER se queda sin forma de guardar. Van juntos.
    """
    assert 'v-model="workorderData.clasificacion"' in indice, (
        "Falta el selector de clasificación en la Pre Work Order")
    for clase in ("A", "AA", "AAA"):
        assert f'<option value="{clase}">' in indice, f"Falta la opción {clase}"


def test_la_clasificacion_viaja_en_el_payload(indice):
    """Un campo que se captura y no se manda es peor que no tenerlo."""
    assert "clasificacion: workorderData.value.clasificacion" in indice


def test_el_formulario_no_deja_guardar_sin_clasificacion(indice):
    """
    La validación del cliente evita el viaje de ida y vuelta para un rechazo que
    el backend ya sabe dar. Las dos existen: esta es comodidad, la del backend
    es la que manda.
    """
    assert "Falta la clasificación" in indice


def test_todo_reset_del_formulario_limpia_la_clasificacion(indice):
    """
    Igual que `cotizador`, la clasificación se reinicia en los cuatro sitios que
    vacían `workorderData`. Un reset que la olvida arrastra la clase de la orden
    anterior a la siguiente, que es el peor fallo posible: silencioso y con un
    SLA equivocado.
    """
    bloques = re.findall(r"workorderData\.value\s*=\s*\{[\s\S]{0,900}?\n\s*\};", indice)
    assert bloques, "No se encontró ningún reset de `workorderData`"
    for bloque in bloques:
        assert re.search(r"clasificacion:\s*''", bloque), (
            "Un reset de `workorderData` no limpia la clasificación")


# ----------------------------------------------------------------------
# 6. Los dos caminos de fallo del reparto
# ----------------------------------------------------------------------

def test_un_responsable_que_no_resuelve_a_nadie_no_inventa_hoja():
    """
    `"(VENTAS)"` es el sufijo suelto, no una persona: `hoja_de_persona` lo deja
    en vacío. Sin este descarte la línea acabaría en una hoja sin nombre, que es
    peor que perderla: nadie la ve y nadie sabe que existe.
    """
    assert work_order.tareas_de_programa(
        [_linea(responsable="(VENTAS)")], CABECERA) == []


def test_si_la_base_rechaza_una_linea_el_error_llega_al_usuario():
    """
    Un rechazo de la base no se traga en silencio: viaja hasta la respuesta del
    endpoint con la hoja y el motivo, que es lo que hace falta para arreglarlo.
    """
    class _Rechaza:
        def guardar(self, hoja, filas, como_copia=False):
            class _R:
                exito = False
                mensaje = "columna inexistente"
            return _R()

    errores = work_order._repartir_programa(
        _Rechaza(),
        {"programa": [_linea(responsable="TERESA GARZA")]},
        {"FOLIO": FOLIO, "AREA": "ELECTROMECANICA", "CLASIFICACION": "AA"},
    )

    assert len(errores) == 1
    assert "TERESA GARZA" in errores[0]
    assert "columna inexistente" in errores[0]
