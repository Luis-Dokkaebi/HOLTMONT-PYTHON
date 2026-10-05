"""
Un tracker sin actividades todavía tiene que enseñar sus columnas.

Reporte del dueño (2026-10-05), con captura: el tracker recién dado de alta de
Aviel Juarez Olivares solo pintaba las columnas `#` y 💾 —ni FOLIO, ni
CONCEPTO, ni STATUS— y así no hay dónde capturar la primera actividad.

La causa: con la base, los encabezados se **descubren de las filas** de
`tasks` (`build_header_map`). Cero filas, cero encabezados: `get_sheet_values`
devolvía `None` y `/api/data` respondía `headers: []`. En Apps Script no
pasaba porque la hoja nueva ya nacía con su fila de encabezados.

Lo que se fija aquí: si la hoja es el tracker de una persona del organigrama,
la matriz vacía lleva la fila de encabezados de `TASK_HEADER_MAP`. Una hoja
que nadie reconoce sigue respondiendo como antes —sin encabezados inventados—
para no fabricar un tracker para cualquier texto que llegue por la URL.
"""

from __future__ import annotations

import pytest

from api.services import sheets
from api.services.sheets import TASK_HEADER_MAP


class SinFilas:
    """Doble de `sb_manager` para una base donde la persona aún no tiene nada."""

    def select(self, table, filters=None):
        return []

    def select_in(self, table, column, values):
        return []

    def select_distinct(self, table, column):
        return []

    def get_sheet_values(self, sheet_name):
        return []


@pytest.fixture
def base_vacia(monkeypatch):
    monkeypatch.setattr(sheets, "sb_manager", SinFilas())
    monkeypatch.setattr(sheets.gs_manager, "is_mock", True, raising=False)
    sheets.reset_source_sheet_cache()
    yield
    sheets.reset_source_sheet_cache()


ENCABEZADOS = [visible for visible, _ in TASK_HEADER_MAP]


@pytest.mark.parametrize("hoja", [
    "AVIEL JUAREZ OLIVARES",   # el caso reportado: alta nueva, cero actividades
    "VANESSA DE LARA",         # cualquier otra persona con tracker vacío
    "aviel juarez olivares",   # el nombre llega con otra capitalización
])
def test_un_tracker_vacio_trae_sus_encabezados(base_vacia, hoja):
    from api.main import get_data

    respuesta = get_data(sheet=hoja)

    assert respuesta["success"] is True
    assert respuesta["headers"] == ENCABEZADOS
    assert respuesta["data"] == []
    assert respuesta["history"] == []


def test_la_matriz_vacia_es_solo_la_fila_de_encabezados(base_vacia):
    assert sheets.gs_manager.get_sheet_values("AVIEL JUAREZ OLIVARES") == [ENCABEZADOS]


def test_una_hoja_que_no_es_de_nadie_no_inventa_encabezados(base_vacia):
    from api.main import get_data

    respuesta = get_data(sheet="HOJA QUE NO EXISTE")
    assert respuesta["headers"] == []
    assert respuesta["data"] == []


@pytest.mark.parametrize("hoja", [None, "", "PPCV3", "ANTONIA_VENTAS"])
def test_sin_persona_no_hay_encabezados_de_tracker(hoja):
    """Sin nombre, el PPC maestro y el core de ventas no son trackers de nadie."""
    assert sheets._encabezados_de_tracker(hoja) is None


@pytest.mark.parametrize("values,esperado", [
    ([ENCABEZADOS], ENCABEZADOS),
    ([["FOLIO", "", "CONCEPTO", "STATUS"]], ["FOLIO", "CONCEPTO", "STATUS"]),
    ([["una fila", "cualquiera"]], []),   # no es una fila de encabezados
    ([], []),
])
def test_encabezados_de_una_hoja_sin_filas(values, esperado):
    from api.main import _encabezados_sin_filas

    assert _encabezados_sin_filas(values) == esperado
