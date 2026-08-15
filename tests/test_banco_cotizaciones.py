"""
El Banco de Cotizaciones: las cotizaciones de la base agrupadas por periodo.

La vista es un recorrido de cuatro pasos —año, mes, cliente, carpeta— y termina
en una tabla con cinco columnas: FECHA INICIO, AREA, CONCEPTO, VENDEDOR y
ESTATUS. Lo que se fija aquí son las tres cosas que estaban mal el 2026-08-15,
cuando el dueño lo abrió contra la base real:

1. **El mes se decidía con la columna equivocada.** `fetch_info_bank_companies`
   buscaba la fecha en `["FECHA INICIO", "FECHA", "ALTA", "FECHA ALTA"]`, y en
   una fila de `quotes` la columna se llama **`F. INICIO`** (así la publica
   `QUOTE_HEADER_MAP`). Ninguna clave coincidía, así que caía en `FECHA`, otra
   columna del esquema, y el cliente aparecía bajo el mes de una fecha que no es
   la de inicio. La regla del dueño es explícita: el periodo lo manda F. INICIO.

2. **La tabla salía sin fecha.** `fetch_info_bank_data` devolvía la fila cruda y
   la vista lee `file.FECHA_INICIO`; la fila trae `F. INICIO`, así que la
   primera columna se pintaba vacía en todas las cotizaciones (se ve en la
   captura del reporte). El original en `CODIGO.js` sí normaliza los nombres
   antes de responder: aquí se recupera esa normalización.

3. **Solo se leía la tabla maestra.** Se consultaba únicamente `ANTONIA_VENTAS`,
   y las cotizaciones viven repartidas entre esa partición y la de cada vendedor
   (`<Vendedor> (VENTAS)`). Todo lo que un vendedor trabaja quedaba fuera del
   banco. Ahora se recorren todas las particiones de `quotes` y se deduplica por
   folio, porque una misma cotización vive en dos hojas por diseño (la clave de
   `quotes` es `(folio, source_sheet)`).
"""

from __future__ import annotations

import pytest

# Encabezados tal como los publica `QUOTE_HEADER_MAP`: la fecha de inicio es
# "F. INICIO" y existe además una columna "FECHA" que NO es la de inicio.
ENCABEZADOS = ["FOLIO", "AREA", "CLIENTE", "CONCEPTO", "VENDEDOR",
               "F. VISITA", "F. INICIO", "ESTATUS", "COTIZACION", "FECHA"]

HOJA_MAESTRA = "ANTONIA_VENTAS"
HOJA_VENDEDOR = "RAMIRO RODRIGUEZ (VENTAS)"


def _fila(folio, cliente, f_inicio, *, area="CONSTRUCCION", concepto="FACTORY WORD",
          vendedor="RAMIRO RODRIGUEZ", estatus="ASIGNADO", cotizacion="", fecha=""):
    return [folio, area, cliente, concepto, vendedor, "", f_inicio, estatus, cotizacion, fecha]


HOJAS = {
    HOJA_MAESTRA: [
        ENCABEZADOS,
        # Junio 2026 por F. INICIO, aunque `FECHA` diga otro mes: manda F. INICIO.
        _fila("AV-1222", "DANFOSS 2", "2026-06-01", fecha="2026-09-15"),
        _fila("AV-1300", "ESSITY", "2026-06-20", vendedor="TOÑITA"),
        # Fuera del periodo.
        _fila("AV-1400", "ALCOM", "2026-07-02"),
        # Sin cliente: no puede colgar de ninguna tarjeta.
        _fila("AV-1500", "", "2026-06-05"),
    ],
    HOJA_VENDEDOR: [
        ENCABEZADOS,
        # La copia asignada de AV-1222: misma cotización, otra partición.
        _fila("AV-1222", "DANFOSS 2", "2026-06-01"),
        # Cotización que solo existe en la hoja del vendedor.
        _fila("RR-0007", "MARMON FOOD", "2026-06-11"),
    ],
}


@pytest.fixture
def banco(monkeypatch):
    from api.services import sheets, tracker_store

    monkeypatch.setattr(tracker_store, "read_values", lambda n: HOJAS.get(n, []))
    monkeypatch.setattr(sheets, "hojas_de_cotizaciones", lambda: list(HOJAS))
    return tracker_store


# --- Clientes del mes (tarjetas) --------------------------------------

def test_los_clientes_se_agrupan_por_f_inicio(banco):
    """AV-1222 tiene F. INICIO en junio y `FECHA` en septiembre: manda junio."""
    nombres = [c["name"] for c in banco.fetch_info_bank_companies(2026, "Junio")["data"]]

    assert "DANFOSS 2" in nombres
    assert "ALCOM" not in nombres          # su F. INICIO es de julio
    assert banco.fetch_info_bank_companies(2026, "Septiembre")["data"] == []


def test_los_clientes_incluyen_las_hojas_de_los_vendedores(banco):
    nombres = [c["name"] for c in banco.fetch_info_bank_companies(2026, "Junio")["data"]]

    assert "MARMON FOOD" in nombres        # solo existe en la hoja del vendedor
    assert nombres == sorted(nombres)


def test_el_cliente_no_se_cuenta_dos_veces_por_la_copia_asignada(banco):
    """AV-1222 vive en dos particiones y es una sola cotización."""
    tarjeta = next(c for c in banco.fetch_info_bank_companies(2026, "Junio")["data"]
                   if c["name"] == "DANFOSS 2")

    assert tarjeta["count"] == 1


def test_los_clientes_ignoran_filas_sin_cliente(banco):
    nombres = [c["name"] for c in banco.fetch_info_bank_companies(2026, "Junio")["data"]]

    assert "" not in nombres
    assert len(nombres) == len(set(nombres))


# --- Cotizaciones del cliente (tabla) ---------------------------------

def test_la_tabla_trae_las_cinco_columnas_de_la_vista(banco):
    filas = banco.fetch_info_bank_data(2026, "Junio", "DANFOSS 2")["data"]

    assert len(filas) == 1
    fila = filas[0]
    for columna in ("FECHA_INICIO", "AREA", "CONCEPTO", "VENDEDOR", "ESTATUS"):
        assert columna in fila, f"la vista lee file.{columna}"
    assert fila["AREA"] == "CONSTRUCCION"
    assert fila["CONCEPTO"] == "FACTORY WORD"
    assert fila["VENDEDOR"] == "RAMIRO RODRIGUEZ"
    assert fila["ESTATUS"] == "ASIGNADO"
    assert fila["FOLIO"] == "AV-1222"


def test_la_fecha_de_inicio_llega_en_el_formato_de_la_vista(banco):
    """
    `formatDisplayDate` deja pasar tal cual lo que no sea dd/mm/aa(aa), así que
    un `date` de Postgres ("2026-06-01") se pintaría en ISO en medio de una
    tabla que en todas partes usa dd/mm/aa.
    """
    fila = banco.fetch_info_bank_data(2026, "Junio", "DANFOSS 2")["data"][0]

    assert fila["FECHA_INICIO"] == "01/06/26"


def test_la_tabla_recorre_todas_las_particiones_de_cotizaciones(banco):
    filas = banco.fetch_info_bank_data(2026, "Junio", "MARMON FOOD")["data"]

    assert [f["FOLIO"] for f in filas] == ["RR-0007"]


def test_la_copia_asignada_no_duplica_la_cotizacion(banco):
    filas = banco.fetch_info_bank_data(2026, "Junio", "")["data"]
    folios = [f["FOLIO"] for f in filas]

    assert folios.count("AV-1222") == 1


def test_la_tabla_ordena_por_fecha_de_inicio(banco):
    filas = banco.fetch_info_bank_data(2026, "Junio", "")["data"]

    assert [f["FOLIO"] for f in filas] == ["AV-1222", "RR-0007", "AV-1300"]


def test_la_tabla_respeta_el_periodo_de_f_inicio(banco):
    """AV-1400 (julio) no puede colarse en junio, ni AV-1222 en septiembre."""
    junio = [f["FOLIO"] for f in banco.fetch_info_bank_data(2026, "Junio", "")["data"]]

    assert "AV-1400" not in junio
    assert banco.fetch_info_bank_data(2026, "Septiembre", "")["data"] == []


def test_un_año_ilegible_cae_en_el_año_en_curso_y_no_revienta(banco, monkeypatch):
    """La vista manda el año como texto; uno que no sea número no puede tumbar
    la pantalla, así que se usa el año en curso, como hacía el original."""
    from datetime import datetime

    class Fijo(datetime):
        @classmethod
        def now(cls, tz=None):
            return datetime(2026, 6, 15)

    monkeypatch.setattr("api.services.tracker_store.datetime", Fijo)
    res = banco.fetch_info_bank_data("no-es-un-año", "Junio", "DANFOSS 2")

    assert res["success"] is True
    assert [f["FOLIO"] for f in res["data"]] == ["AV-1222"]


def test_los_endpoints_del_banco_responden_lo_que_pinta_la_vista(banco):
    """
    El contrato completo `index.html` -> `api_service.js` -> `api/main.py`: la
    vista llama a estos dos endpoints y lee `data[].name` y `data[].FECHA_INICIO`.
    """
    from fastapi.testclient import TestClient

    from api.main import app

    cliente = TestClient(app)

    empresas = cliente.get("/api/legacy/infoBankCompanies",
                           params={"year": "2026", "month": "Junio"}).json()
    assert "DANFOSS 2" in [c["name"] for c in empresas["data"]]

    cotizaciones = cliente.get("/api/legacy/infoBankData",
                               params={"year": "2026", "month": "Junio",
                                       "company": "DANFOSS 2", "folder": "COTIZACIONES"}).json()
    assert [f["FECHA_INICIO"] for f in cotizaciones["data"]] == ["01/06/26"]
    assert cotizaciones["headers"] == ["FECHA INICIO", "AREA", "CONCEPTO", "VENDEDOR", "ESTATUS"]


def test_el_banco_sigue_en_pie_si_no_se_pueden_listar_las_particiones(monkeypatch):
    """
    Sin credenciales el índice de `source_sheet` viene vacío. El banco debe caer
    a la tabla maestra en vez de quedarse sin datos.
    """
    from api.services import sheets, tracker_store

    monkeypatch.setattr(tracker_store, "read_values", lambda n: HOJAS.get(n, []))
    monkeypatch.setattr(sheets, "hojas_de_cotizaciones", lambda: [])

    filas = tracker_store.fetch_info_bank_data(2026, "Junio", "DANFOSS 2")["data"]

    assert [f["FOLIO"] for f in filas] == ["AV-1222"]
