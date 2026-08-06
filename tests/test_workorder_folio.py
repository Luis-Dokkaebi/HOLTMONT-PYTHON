"""
El folio de Work Order, contra `generateWorkOrderFolio` del original.

`api/services/work_order.py` estaba al 51 % de cobertura y la función que arma
el folio —la parte que el usuario ve y por la que busca una orden— no tenía
ninguna prueba. Estas comparan su salida con la del original
(`REAL-HOLTMONT/CODIGO.js:4148-4221`), que es la referencia.

Formato: `{secuencia:4}{iniciales del cliente} {Depto} {ddmmyy}`
Ejemplo:  `1001AC Electro 060826`

Dos divergencias que motivaron el archivo:

  1. `ABBR_MAP` tenía 24 de las 27 entradas del original. Faltaban `FINANZAS`,
     `FACTURACION` y `FACTURACIÓN`, que son departamentos reales del
     organigrama. Sin ellas caían al truncado y daban `Finan` y `Factu` en vez
     de `Finanzas` y `Factura`: el folio de esas áreas salía con otro formato.

  2. La limpieza del nombre del cliente **borraba** los caracteres no
     alfanuméricos en vez de **sustituirlos por un espacio**, que es lo que
     hace el original (`.replace(/[^A-Z0-9]/g, ' ')`). Con `COCA-COLA` el
     original saca `CC` (dos palabras) y esta versión sacaba `CO` (una sola).
     Cualquier cliente con guion, punto o `&` generaba un folio distinto al que
     lleva usando la empresa.
"""

from __future__ import annotations

from datetime import datetime
from typing import Any

import pytest

from api.services import work_order


@pytest.fixture(autouse=True)
def _secuencia_fija(monkeypatch: Any) -> None:
    """Fija la secuencia para que el folio sea determinista."""
    monkeypatch.setattr(work_order, "get_next_sequence", lambda *a, **k: "1001")


def _hoy() -> str:
    return datetime.now().strftime("%d%m%y")


# --- Abreviaturas de departamento (las 27 del original) ---------------

ABREVIATURAS_DEL_ORIGINAL = [
    ("ELECTROMECANICA", "Electro"), ("ELECTROMECÁNICA", "Electro"),
    ("CONSTRUCCION", "Const"), ("CONSTRUCCIÓN", "Const"),
    ("MANTENIMIENTO", "Mtto"),
    ("REMODELACION", "Remod"), ("REMODELACIÓN", "Remod"),
    ("REPARACION", "Repar"), ("REPARACIÓN", "Repar"),
    ("RECONFIGURACION", "Reconf"), ("RECONFIGURACIÓN", "Reconf"),
    ("POLIZA", "Poliza"), ("PÓLIZA", "Poliza"),
    ("INSPECCION", "Insp"), ("INSPECCIÓN", "Insp"),
    ("ADMINISTRACION", "Admin"), ("ADMINISTRACIÓN", "Admin"),
    ("MAQUINARIA", "Maq"),
    ("DISEÑO", "Diseño"),
    ("COMPRAS", "Compras"),
    ("VENTAS", "Ventas"),
    ("HVAC", "HVAC"),
    ("FINANZAS", "Finanzas"),
    ("FACTURACION", "Factura"), ("FACTURACIÓN", "Factura"),
    ("SEGURIDAD", "EHS"), ("EHS", "EHS"),
]


@pytest.mark.parametrize(("departamento", "abreviatura"), ABREVIATURAS_DEL_ORIGINAL)
def test_el_departamento_usa_la_abreviatura_del_original(departamento: str,
                                                         abreviatura: str) -> None:
    folio = work_order.generate_work_order_folio("ACME CORP", departamento)
    assert folio == f"1001AC {abreviatura} {_hoy()}", (
        f"{departamento} debería abreviarse {abreviatura!r}"
    )


def test_estan_las_27_abreviaturas_del_original() -> None:
    """
    Control de conjunto: el mapa completo, no una muestra.

    Faltaban tres y nadie se enteró hasta que alguien de Finanzas levantó una
    orden. Esto lo convierte en una prueba en vez de en un reporte.
    """
    faltan = [d for d, a in ABREVIATURAS_DEL_ORIGINAL
              if work_order.generate_work_order_folio("A B", d).split()[1] != a]
    assert faltan == [], f"departamentos sin su abreviatura del original: {faltan}"


@pytest.mark.parametrize(("departamento", "esperado"), [
    # >6 caracteres: primera letra + 4 siguientes en minúscula.
    ("PRESUPUESTOS", "Presu"),
    ("LIMPIEZA", "Limpi"),
    # <=6: primera letra + resto en minúscula.
    ("CEO", "Ceo"),
    ("RH", "Rh"),
])
def test_un_departamento_fuera_del_mapa_cae_al_truncado_del_original(
        departamento: str, esperado: str) -> None:
    folio = work_order.generate_work_order_folio("ACME CORP", departamento)
    assert folio.split()[1] == esperado


# --- Iniciales del cliente -------------------------------------------

@pytest.mark.parametrize(("cliente", "iniciales"), [
    ("ACME CORP", "AC"),
    ("DANFOSS", "DA"),
    # El original sustituye la puntuación por un espacio, así que estos son
    # dos palabras y no una.
    ("COCA-COLA", "CC"),
    ("GRUPO.MODELO", "GM"),
    ("HOLT&MONT", "HM"),
    ("PANASONIC DE MEXICO", "PD"),
    # Sin nombre, el original usa XX.
    ("", "XX"),
    (None, "XX"),
])
def test_las_iniciales_del_cliente_salen_como_en_el_original(cliente: Any,
                                                             iniciales: str) -> None:
    folio = work_order.generate_work_order_folio(cliente, "HVAC")
    assert folio.startswith(f"1001{iniciales} "), f"folio obtenido: {folio!r}"


def test_el_folio_completo_tiene_el_formato_del_original() -> None:
    """`{secuencia:4}{XX} {Depto} {ddmmyy}` — tal cual lo lee la gente."""
    assert work_order.generate_work_order_folio("ACME CORP", "HVAC") == \
        f"1001AC HVAC {_hoy()}"


def test_sin_departamento_se_usa_General_como_el_original() -> None:
    folio = work_order.generate_work_order_folio("ACME CORP", None)
    assert folio.split()[1] == "Gener"
