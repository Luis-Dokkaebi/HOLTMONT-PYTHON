"""
Orden de la tabla de cotizaciones (`ANTONIA_VENTAS` y las hojas `(VENTAS)`).

La tabla se ordenaba por el orden de la hoja, no por fecha: `index.html` tomaba
las filas tal como llegaban y las invertía con `staffTrackerSortAsc`. Con las
filas dispersas en la hoja, una cotización de mayo aparecía debajo de una de
julio y no había forma de leer la tabla por antigüedad.

Lo que se pide y lo que aquí se fija:

  * Las hojas de ventas abren de la cotización **más vieja a la más nueva**,
    tomando `F. INICIO` como fecha.
  * "Invertir Orden" las pone de la **más nueva a la más vieja**.
  * Las filas recién agregadas (`_isNew`) siguen arriba en los dos sentidos:
    `addNewRow` las mete con `unshift` y resalta la primera fila
    (`pulseNewRow('trackerTable', 'first')`); si se fueran al final, el
    resaltado marcaría otra fila.
  * Los trackers (las hojas que no son de ventas) conservan su comportamiento:
    orden de la hoja invertido, que es lo que había antes de este cambio.

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
        const ventasSortAsc = ref(true);

        {es_ventas}
        {region}

        for (let i = 0; i < {invertir}; i++) toggleTrackerSort();
        console.log(JSON.stringify({{
            folios: filteredStaffTrackerData.value.map(f => f.FOLIO),
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
    assert resultado["folios"] == ["AV-1190", "AV-1245", "AV-0009", "AV-0060"], (
        "la tabla debe abrir por F. INICIO ascendente: mayo, junio, junio, julio"
    )
    assert resultado["asc"] is True, "el icono debe indicar orden ascendente"


def test_invertir_orden_pone_la_mas_nueva_al_principio() -> None:
    resultado = _orden("ANTONIA_VENTAS", FILAS_VENTAS, invertir=1)
    assert resultado["folios"] == ["AV-0060", "AV-1245", "AV-0009", "AV-1190"], (
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


def test_los_empates_conservan_el_orden_de_la_hoja() -> None:
    """AV-1245 y AV-0009 son del mismo día: no se barajan entre recargas."""
    assert _orden("ANTONIA_VENTAS", FILAS_VENTAS)["folios"][1:3] == ["AV-1245", "AV-0009"]


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
    assert folios == ["AV-1190", "AV-1245", "AV-0009", "AV-0060", "AV-MALA"]


def test_sin_columna_de_fecha_la_hoja_de_ventas_conserva_su_orden() -> None:
    """
    Sin `F. INICIO` no hay por dónde ordenar: la tabla se comporta como antes
    —orden de la hoja invertido— en vez de quedarse quieta.
    """
    filas = [{"FOLIO": "A"}, {"FOLIO": "B"}, {"FOLIO": "C"}]
    assert _orden("ANTONIA_VENTAS", filas)["folios"] == ["C", "B", "A"]
    assert _orden("ANTONIA_VENTAS", filas, invertir=1)["folios"] == ["A", "B", "C"]


# ---------------------------------------------------------------------------
# Los trackers no se tocan
# ---------------------------------------------------------------------------

def test_el_tracker_de_tareas_conserva_el_orden_que_ya_tenia() -> None:
    """
    `ANTONIA PINEDA LOPEZ` es su tracker, no su hoja de ventas.

    Ahí la columna de fecha se llama `FECHA` y el orden sigue siendo el de la
    hoja invertido: este cambio es de la vista de cotizaciones.
    """
    filas = [
        {"FOLIO": "JO-1", "FECHA": "03/07/26"},
        {"FOLIO": "JO-2", "FECHA": "28/05/26"},
        {"FOLIO": "JO-3", "FECHA": "19/06/26"},
    ]
    assert _orden("ANTONIA PINEDA LOPEZ", filas)["folios"] == ["JO-3", "JO-2", "JO-1"]
    assert _orden("ANTONIA PINEDA LOPEZ", filas, invertir=1)["folios"] == ["JO-1", "JO-2", "JO-3"]


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
