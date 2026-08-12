"""
Orden de la tabla del tracker: cotizaciones y tareas.

La tabla se ordenaba por el orden de la hoja, no por fecha: `index.html` tomaba
las filas tal como llegaban y las invertía con `staffTrackerSortAsc`. Con las
filas dispersas en la hoja, una cotización de mayo aparecía debajo de una de
julio y no había forma de leer la tabla por antigüedad.

Lo que se pide y lo que aquí se fija:

  * Las hojas de ventas abren de la cotización **más vieja a la más nueva**,
    tomando `F. INICIO` como fecha.
  * Los trackers hacen lo mismo con su propia columna de alta, `FECHA`: las
    tareas abren de la más vieja a la más nueva (decisión del dueño,
    2026-08-11: "necesito que las tareas se inicien desde la más vieja a la más
    nueva usando Fecha, y si hay empate en la fecha, desempata con folio").
  * "Invertir Orden" las pone de la **más nueva a la más vieja**.
  * Las filas del mismo día desempatan por **FOLIO** ascendente en los dos
    sentidos. El orden de la hoja no sirve: cambia con cada recarga.
  * Las filas recién agregadas (`_isNew`) siguen arriba en los dos sentidos:
    `addNewRow` las mete con `unshift` y resalta la primera fila
    (`pulseNewRow('trackerTable', 'first')`); si se fueran al final, el
    resaltado marcaría otra fila.
  * Cada tabla mira **solo su** columna: una hoja de ventas nunca se ordena por
    `FECHA` (ahí es una columna heredada y oculta) y un tracker nunca por
    `F. INICIO`.
  * Sin columna de fecha, la tabla conserva el comportamiento de siempre: orden
    de la hoja invertido.

Se evalúa el código **real** de `index.html` con Node —la región que va de
`COLUMNAS_FECHA_DE_ORDEN` a `filteredStaffTrackerData`— sobre `ref` y `computed`
de mentira. Una prueba de texto pasaría aunque el orden estuviera al revés.
"""

from __future__ import annotations

import json
import os
import re
import shutil
import subprocess

import pytest

RAIZ = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
INDEX = os.path.join(RAIZ, "index.html")

pytestmark = pytest.mark.skipif(shutil.which("node") is None,
                                reason="node no está instalado")


def _fuente() -> str:
    with open(INDEX, encoding="utf-8") as fh:
        return fh.read()


def _bloque(patron: str, nombre: str) -> str:
    m = re.search(patron, _fuente(), re.S)
    assert m, f"no se encontró {nombre} en index.html"
    return m.group(0)


def _guion(hoja: str, filas: list, *, filtros: dict | None = None,
           invertir: int = 0) -> str:
    """Corre el orden real de la vista sobre `filas` y devuelve los FOLIO."""
    es_ventas = _bloque(r"const esHojaDeVentas = .*?\n      \};",
                        "esHojaDeVentas")
    region = _bloque(
        r"const COLUMNAS_FECHA_DE_ORDEN = \[.*?"
        r"const filteredStaffTrackerData = computed\(\(\) => \{.*?\n      \}\);",
        "la región de orden de la tabla (COLUMNAS_FECHA_DE_ORDEN…"
        "filteredStaffTrackerData)")
    return f"""
        const ref = (v) => ({{ value: v }});
        const computed = (f) => ({{ get value() {{ return f(); }} }});

        const staffTracker = ref({{
            name: {json.dumps(hoja)},
            headers: [],
            data: {json.dumps(filas)} }});
        const staffTrackerFilters = ref({json.dumps(filtros or {})});
        const staffTrackerSortAsc = ref(false);
        const ordenFechaAsc = ref(true);

        {es_ventas}
        {region}

        for (let i = 0; i < {invertir}; i++) toggleTrackerSort();
        console.log(JSON.stringify({{
            folios: filteredStaffTrackerData.value.map(f => f.FOLIO || f.ID || ""),
            asc: trackerOrdenAsc.value }}));
    """


def _orden(hoja: str, filas: list, *, filtros: dict | None = None,
           invertir: int = 0) -> dict:
    salida = subprocess.run(
        ["node", "-e", _guion(hoja, filas, filtros=filtros, invertir=invertir)],
        capture_output=True, text=True, timeout=30, check=False)
    assert salida.returncode == 0, f"node falló: {salida.stderr}"
    return json.loads(salida.stdout)


# Las cuatro filas de la captura del dueño, en el desorden en que las trae la
# hoja: julio, mayo, junio 19, junio 19.
FILAS_VENTAS = [
    {"FOLIO": "AV-0060", "CLIENTE": "PANASONIC", "F. VISITA": "2026-07-03",
     "F. INICIO": "2026-07-03"},
    {"FOLIO": "AV-1190", "CLIENTE": "MARMON FOOD", "F. VISITA": "2026-05-28",
     "F. INICIO": "2026-05-28"},
    {"FOLIO": "AV-1245", "CLIENTE": "WCRY", "F. VISITA": "2026-06-19",
     "F. INICIO": "2026-06-19"},
    {"FOLIO": "AV-0009", "CLIENTE": "DANFOSS 4", "F. VISITA": "2026-06-19",
     "F. INICIO": "2026-06-19"},
]


# ---------------------------------------------------------------------------
# Cotizaciones: de la más vieja a la más nueva
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("hoja", ["ANTONIA_VENTAS", "RAMIRO RIOS (VENTAS)"])
def test_las_hojas_de_ventas_abren_de_la_mas_vieja_a_la_mas_nueva(hoja: str) -> None:
    resultado = _orden(hoja, FILAS_VENTAS)
    assert resultado["folios"] == ["AV-1190", "AV-0009", "AV-1245", "AV-0060"], (
        "la tabla debe abrir por F. INICIO ascendente: mayo, junio, junio, julio"
    )
    assert resultado["asc"] is True, "el icono debe indicar orden ascendente"


def test_invertir_orden_pone_la_mas_nueva_al_principio() -> None:
    resultado = _orden("ANTONIA_VENTAS", FILAS_VENTAS, invertir=1)
    assert resultado["folios"] == ["AV-0060", "AV-0009", "AV-1245", "AV-1190"], (
        "tras invertir, de la más nueva a la más vieja: julio, junio, junio, mayo"
    )
    assert resultado["asc"] is False


def test_invertir_dos_veces_regresa_al_orden_de_apertura() -> None:
    assert (_orden("ANTONIA_VENTAS", FILAS_VENTAS, invertir=2)["folios"]
            == _orden("ANTONIA_VENTAS", FILAS_VENTAS)["folios"])


def test_las_dos_notaciones_de_fecha_se_ordenan_juntas() -> None:
    """
    En las mismas hojas conviven `dd/mm/aa` y `aaaa-mm-dd`.

    Es el defecto que `new Date(cadena)` esconde: lee `aaaa-mm-dd` como UTC y
    en un huso negativo la corre al día anterior, con lo que dos fechas del
    mismo día se ordenarían al revés según cómo estén escritas.
    """
    filas = [
        {"FOLIO": "NUEVA", "F. INICIO": "2026-07-03"},
        {"FOLIO": "VIEJA", "F. INICIO": "28/05/26"},
        {"FOLIO": "MEDIA", "F. INICIO": "19/06/2026"},
    ]
    assert _orden("ANTONIA_VENTAS", filas)["folios"] == ["VIEJA", "MEDIA", "NUEVA"]


def test_las_cotizaciones_del_mismo_dia_desempatan_por_folio() -> None:
    """
    AV-1245 y AV-0009 son del mismo 19 de junio y en la hoja vienen en ese
    orden. El desempate es por folio, así que AV-0009 va primero.

    El orden de la hoja no sirve de desempate: cambia con cada recarga y las
    dos filas se barajarían solas.
    """
    assert _orden("ANTONIA_VENTAS", FILAS_VENTAS)["folios"][1:3] == ["AV-0009", "AV-1245"]


def test_el_desempate_por_folio_no_se_invierte_con_el_boton() -> None:
    """Dentro de un mismo día el folio se busca siempre en el mismo lugar."""
    assert _orden("ANTONIA_VENTAS", FILAS_VENTAS, invertir=1)["folios"][1:3] == ["AV-0009", "AV-1245"]


def test_el_desempate_cuenta_el_numero_del_folio_no_su_texto() -> None:
    """AV-9 antes que AV-10: comparados como texto, AV-10 iría primero."""
    mismo_dia = [
        {"FOLIO": "AV-10", "F. INICIO": "19/06/26"},
        {"FOLIO": "AV-9", "F. INICIO": "19/06/26"},
        {"FOLIO": "AV-100", "F. INICIO": "19/06/26"},
    ]
    assert _orden("ANTONIA_VENTAS", mismo_dia)["folios"] == ["AV-9", "AV-10", "AV-100"]


def test_una_fila_con_fecha_y_sin_folio_va_al_final_de_su_dia() -> None:
    mismo_dia = [
        {"FOLIO": "", "F. INICIO": "19/06/26"},
        {"FOLIO": "AV-1245", "F. INICIO": "19/06/26"},
    ]
    assert _orden("ANTONIA_VENTAS", mismo_dia)["folios"] == ["AV-1245", ""]


# ---------------------------------------------------------------------------
# Filas que no tienen por dónde ordenarse
# ---------------------------------------------------------------------------

def test_la_fila_recien_agregada_se_queda_arriba_en_los_dos_sentidos() -> None:
    """`addNewRow` la mete con `unshift` y resalta la primera fila."""
    filas = [{"FOLIO": "", "F. INICIO": "", "_isNew": True}] + FILAS_VENTAS
    assert _orden("ANTONIA_VENTAS", filas)["folios"][0] == ""
    assert _orden("ANTONIA_VENTAS", filas, invertir=1)["folios"][0] == ""


def test_una_fila_guardada_sin_fecha_va_al_final_pero_no_desaparece() -> None:
    filas = FILAS_VENTAS + [{"FOLIO": "AV-SIN", "F. INICIO": ""}]
    for invertir in (0, 1):
        folios = _orden("ANTONIA_VENTAS", filas, invertir=invertir)["folios"]
        assert len(folios) == 5, "no se pierde ninguna fila al ordenar"
        assert folios[-1] == "AV-SIN"


def test_una_fecha_ilegible_no_tira_la_tabla() -> None:
    filas = FILAS_VENTAS + [{"FOLIO": "AV-MALA", "F. INICIO": "sin fecha"}]
    folios = _orden("ANTONIA_VENTAS", filas)["folios"]
    assert folios == ["AV-1190", "AV-0009", "AV-1245", "AV-0060", "AV-MALA"]


def test_sin_columna_de_fecha_la_hoja_de_ventas_conserva_su_orden() -> None:
    """
    Sin `F. INICIO` no hay por dónde ordenar: la tabla se comporta como antes
    —orden de la hoja invertido— en vez de quedarse quieta.
    """
    filas = [{"FOLIO": "A"}, {"FOLIO": "B"}, {"FOLIO": "C"}]
    assert _orden("ANTONIA_VENTAS", filas)["folios"] == ["C", "B", "A"]
    assert _orden("ANTONIA_VENTAS", filas, invertir=1)["folios"] == ["A", "B", "C"]


# ---------------------------------------------------------------------------
# Los trackers: la misma regla sobre su columna `FECHA`
# ---------------------------------------------------------------------------

# Cuatro tareas del tracker en el desorden en que las trae la hoja, con dos
# empatadas el 19 de junio para probar el desempate por folio.
FILAS_TRACKER = [
    {"FOLIO": "SP-0060", "CONCEPTO": "REVISAR PLANOS", "FECHA": "03/07/26"},
    {"FOLIO": "SP-1190", "CONCEPTO": "VISITA OBRA", "FECHA": "28/05/26"},
    {"FOLIO": "SP-1245", "CONCEPTO": "COTIZAR MATERIAL", "FECHA": "19/06/26"},
    {"FOLIO": "SP-0009", "CONCEPTO": "ENTREGA", "FECHA": "19/06/26"},
]


def test_el_tracker_abre_de_la_tarea_mas_vieja_a_la_mas_nueva() -> None:
    """
    `ANTONIA PINEDA LOPEZ` es su tracker, no su hoja de ventas: ahí la columna
    de alta se llama `FECHA`.

    Antes de este cambio el tracker conservaba el orden de la hoja invertido.
    El dueño pidió (2026-08-11) la misma lectura por antigüedad que ya tenía
    la tabla de ventas.
    """
    resultado = _orden("ANTONIA PINEDA LOPEZ", FILAS_TRACKER)
    assert resultado["folios"] == ["SP-1190", "SP-0009", "SP-1245", "SP-0060"], (
        "las tareas deben abrir por FECHA ascendente: mayo, junio, junio, julio"
    )
    assert resultado["asc"] is True, "el icono debe indicar orden ascendente"


def test_invertir_orden_en_el_tracker_pone_la_tarea_mas_nueva_al_principio() -> None:
    resultado = _orden("ANTONIA PINEDA LOPEZ", FILAS_TRACKER, invertir=1)
    assert resultado["folios"] == ["SP-0060", "SP-0009", "SP-1245", "SP-1190"]
    assert resultado["asc"] is False


def test_las_tareas_del_mismo_dia_desempatan_por_folio() -> None:
    """
    SP-1245 y SP-0009 son del mismo 19 de junio y en la hoja vienen en ese
    orden. Desempata el folio, así que SP-0009 va primero, y sigue igual tras
    invertir: dentro de un día el folio se busca siempre en el mismo lugar.
    """
    assert _orden("ANTONIA PINEDA LOPEZ", FILAS_TRACKER)["folios"][1:3] == ["SP-0009", "SP-1245"]
    assert (_orden("ANTONIA PINEDA LOPEZ", FILAS_TRACKER, invertir=1)["folios"][1:3]
            == ["SP-0009", "SP-1245"])


def test_el_tracker_desempata_por_ID_cuando_la_fila_no_trae_FOLIO() -> None:
    """Las hojas viejas rotulan la columna `ID`: es el par que ya busca
    `find_row_object` en el backend."""
    mismo_dia = [
        {"ID": "SP-10", "FECHA": "19/06/26"},
        {"ID": "SP-9", "FECHA": "19/06/26"},
    ]
    assert _orden("ANTONIA PINEDA LOPEZ", mismo_dia)["folios"] == ["SP-9", "SP-10"]


def test_la_tarea_recien_agregada_se_queda_arriba_en_el_tracker() -> None:
    filas = [{"FOLIO": "", "FECHA": "", "_isNew": True}] + FILAS_TRACKER
    assert _orden("ANTONIA PINEDA LOPEZ", filas)["folios"][0] == ""
    assert _orden("ANTONIA PINEDA LOPEZ", filas, invertir=1)["folios"][0] == ""


def test_la_tarea_sin_fecha_va_al_final_pero_no_desaparece() -> None:
    filas = FILAS_TRACKER + [{"FOLIO": "SP-SIN", "FECHA": ""}]
    for invertir in (0, 1):
        folios = _orden("ANTONIA PINEDA LOPEZ", filas, invertir=invertir)["folios"]
        assert len(folios) == 5
        assert folios[-1] == "SP-SIN"


def test_sin_columna_FECHA_el_tracker_conserva_el_orden_de_la_hoja() -> None:
    """Es el comportamiento de siempre para las hojas que no tienen por dónde
    ordenarse: orden de la hoja invertido."""
    filas = [{"FOLIO": "A"}, {"FOLIO": "B"}, {"FOLIO": "C"}]
    assert _orden("ANTONIA PINEDA LOPEZ", filas)["folios"] == ["C", "B", "A"]
    assert _orden("ANTONIA PINEDA LOPEZ", filas, invertir=1)["folios"] == ["A", "B", "C"]


def test_el_tracker_no_se_ordena_por_la_fecha_de_compromiso() -> None:
    """
    `FECHA_ESTIMADA_FIN` y `FECHA_RESPUESTA` no son la fecha de alta.

    La columna se busca por nombre exacto, no por subcadena: sin `FECHA` la
    tabla se queda con el orden de la hoja en vez de ordenarse por cuándo se
    prometió la entrega.
    """
    filas = [
        {"FOLIO": "SP-1", "FECHA_ESTIMADA_FIN": "03/07/26"},
        {"FOLIO": "SP-2", "FECHA_ESTIMADA_FIN": "28/05/26"},
    ]
    assert _orden("ANTONIA PINEDA LOPEZ", filas)["folios"] == ["SP-2", "SP-1"]


# ---------------------------------------------------------------------------
# Cada tabla mira solo su columna
# ---------------------------------------------------------------------------

def test_la_hoja_de_ventas_no_se_ordena_por_la_columna_FECHA() -> None:
    """
    En las hojas de ventas `FECHA` es una columna heredada que la tabla oculta
    (`COLUMNAS_OCULTAS_VENTAS`) y que no trae la fecha de inicio. Ordenar por
    ella dejaría las cotizaciones en un orden que no se ve por ningún lado.
    """
    filas = [
        {"FOLIO": "AV-1", "FECHA": "03/07/26"},
        {"FOLIO": "AV-2", "FECHA": "28/05/26"},
        {"FOLIO": "AV-3", "FECHA": "19/06/26"},
    ]
    assert _orden("ANTONIA_VENTAS", filas)["folios"] == ["AV-3", "AV-2", "AV-1"], (
        "sin F. INICIO la hoja de ventas conserva el orden de la hoja invertido"
    )


def test_el_tracker_no_se_ordena_por_la_columna_F_INICIO() -> None:
    """Simétrico: `F. INICIO` es de la vista de cotizaciones."""
    filas = [
        {"FOLIO": "SP-1", "F. INICIO": "03/07/26"},
        {"FOLIO": "SP-2", "F. INICIO": "28/05/26"},
    ]
    assert _orden("ANTONIA PINEDA LOPEZ", filas)["folios"] == ["SP-2", "SP-1"]


# ---------------------------------------------------------------------------
# `ALTA` es el área, no una fecha
# ---------------------------------------------------------------------------

# Las mismas cuatro tareas, pero con la fila **completa** que manda el backend:
# `TASK_HEADER_MAP` pone `ALTA` (el área) entre `FOLIO` y `FECHA`. Es la forma
# real de una fila del tracker, y la que rompía el orden.
FILAS_TRACKER_CON_ALTA = [
    {"FOLIO": "SP-0060", "ALTA": "OPERATIVO", "FECHA": "03/07/26",
     "CONCEPTO": "REVISAR PLANOS"},
    {"FOLIO": "SP-1190", "ALTA": "OPERATIVO", "FECHA": "28/05/26",
     "CONCEPTO": "VISITA OBRA"},
    {"FOLIO": "SP-1245", "ALTA": "ADMINISTRATIVO", "FECHA": "19/06/26",
     "CONCEPTO": "COTIZAR MATERIAL"},
    {"FOLIO": "SP-0009", "ALTA": "OPERATIVO", "FECHA": "19/06/26",
     "CONCEPTO": "ENTREGA"},
]


def test_la_columna_ALTA_no_secuestra_el_orden_por_fecha() -> None:
    """
    Reporte del dueño (2026-08-12): «FUNCIÓN INVERTIR ORDEN — no funciona al
    momento de accionar».

    `ALTA` es el **área** (`CODIGO.js:2228`, `ALIAS_DE_HOJA['departamento']`),
    pero estaba listada en `COLUMNAS_FECHA_TRACKER`. Como `fechaDeFila` tomaba
    la primera clave de la fila que casara con la lista, y el backend manda
    `ALTA` antes que `FECHA`, cada fila se ordenaba por su departamento:
    `fechaDeOrden('OPERATIVO')` es `null`, así que las cuatro caían en el
    bloque «sin fecha» y la tabla se quedaba tal como venía de la hoja.

    Con las filas de prueba que no traían `ALTA` el defecto era invisible.
    """
    resultado = _orden("ANTONIA PINEDA LOPEZ", FILAS_TRACKER_CON_ALTA)
    assert resultado["folios"] == ["SP-1190", "SP-0009", "SP-1245", "SP-0060"], (
        "con `ALTA` presente el orden debe seguir siendo por FECHA ascendente"
    )


def test_invertir_orden_funciona_con_la_fila_completa_del_backend() -> None:
    """El síntoma que se ve: el botón no hacía nada."""
    apertura = _orden("ANTONIA PINEDA LOPEZ", FILAS_TRACKER_CON_ALTA)
    invertido = _orden("ANTONIA PINEDA LOPEZ", FILAS_TRACKER_CON_ALTA, invertir=1)

    assert invertido["folios"] == ["SP-0060", "SP-0009", "SP-1245", "SP-1190"]
    assert invertido["folios"] != apertura["folios"], (
        "invertir tiene que cambiar el orden de la tabla, no solo el icono"
    )
    assert invertido["asc"] is False


def test_una_fila_sin_FECHA_no_se_ordena_por_su_area() -> None:
    """
    Sin `FECHA`, la fila va al bloque «sin fecha» y se queda al final: el área
    no es una fecha ni cuando es lo único que hay.
    """
    filas = FILAS_TRACKER_CON_ALTA + [{"FOLIO": "SP-SIN", "ALTA": "OPERATIVO"}]
    folios = _orden("ANTONIA PINEDA LOPEZ", filas)["folios"]
    assert len(folios) == 5, "no se pierde ninguna fila"
    assert folios[-1] == "SP-SIN"


def test_FECHA_ALTA_sigue_sirviendo_para_ordenar() -> None:
    """
    Quitar `ALTA` de la lista no puede llevarse por delante `FECHA ALTA`, que
    sí es la fecha de alta en las hojas que la rotulan así.
    """
    filas = [
        {"FOLIO": "SP-1", "FECHA ALTA": "03/07/26"},
        {"FOLIO": "SP-2", "FECHA ALTA": "28/05/26"},
    ]
    assert _orden("ANTONIA PINEDA LOPEZ", filas)["folios"] == ["SP-2", "SP-1"]
    assert _orden("ANTONIA PINEDA LOPEZ", filas, invertir=1)["folios"] == ["SP-1", "SP-2"]


# ---------------------------------------------------------------------------
# El orden convive con los filtros de columna
# ---------------------------------------------------------------------------

def test_el_filtro_de_columna_se_aplica_antes_de_ordenar() -> None:
    filas = FILAS_VENTAS + [
        {"FOLIO": "AV-9999", "CLIENTE": "WCRY", "F. INICIO": "2026-01-05"},
    ]
    resultado = _orden("ANTONIA_VENTAS", filas, filtros={"CLIENTE": "WCRY"})
    assert resultado["folios"] == ["AV-9999", "AV-1245"], (
        "solo las filas de WCRY, y de la más vieja a la más nueva"
    )
