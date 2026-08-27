"""
Selección de filas para `scripts/sincronizar_espejo_administrador.py`.

`ADMINISTRADOR` es la hoja de control: recibe una copia de cada actividad para
que dirección las vea juntas. En la migración esas copias se importaron con el
avance de ese día y no se volvieron a sincronizar, así que la cotización siguió
avanzando y su espejo se quedó congelado.

Se nota porque el reparto entre activo y `TAREAS REALIZADAS` se calcula al leer
a partir del avance: con la cotización al 100 % y el espejo en 0, la copia
aparece como pendiente para siempre.

La selección es una función pura sobre las dos listas, así que se prueba entera
sin tocar la base (R7). Lo que se fija aquí:

  * Solo se mueve **hacia adelante**. Si el espejo va por delante, alguien puso
    ahí un dato que la cotización no tiene, y elegir por él sería inventar.
  * Solo filas de `ADMINISTRADOR`: las de los trackers reales no se tocan.
  * Una fila sin cotización se queda como está.
"""

from __future__ import annotations

from typing import Any, Dict

from scripts.sincronizar_espejo_administrador import filas_a_sincronizar


def _espejo(folio: str, avance: Any, hoja: str = "ADMINISTRADOR") -> Dict[str, Any]:
    return {"id": f"id-{folio}", "folio": folio, "avance": avance, "source_sheet": hoja}


def _cotizacion(folio: str, avance: Any) -> Dict[str, Any]:
    return {"folio": folio, "avance": avance, "source_sheet": "ANTONIA_VENTAS"}


def test_el_espejo_atrasado_se_pone_al_dia() -> None:
    pendientes = filas_a_sincronizar([_espejo("AV-1", 0)], [_cotizacion("AV-1", 100)])

    assert len(pendientes) == 1
    fila, nuevo = pendientes[0]
    assert fila["folio"] == "AV-1"
    assert nuevo == 100


def test_el_espejo_al_dia_no_se_toca() -> None:
    assert filas_a_sincronizar([_espejo("AV-1", 100)], [_cotizacion("AV-1", 100)]) == []


def test_el_espejo_por_delante_no_se_retrocede() -> None:
    """
    Los 12 casos reales en que el espejo sabe algo que la cotización no.

    Bajarlo seria perder un dato que alguien capturo a proposito.
    """
    assert filas_a_sincronizar([_espejo("AV-1", 100)], [_cotizacion("AV-1", 50)]) == []


def test_una_fila_sin_cotizacion_se_queda_como_esta() -> None:
    assert filas_a_sincronizar([_espejo("AV-9", 0)], [_cotizacion("AV-1", 100)]) == []


def test_las_filas_de_otros_trackers_no_se_tocan() -> None:
    """El script es solo para la hoja espejo, no para el tracker de nadie."""
    filas = [_espejo("AV-1", 0, hoja="LUIS CARLOS"),
             _espejo("AV-2", 0, hoja="ANTONIA PINEDA LOPEZ")]
    assert filas_a_sincronizar(filas, [_cotizacion("AV-1", 100),
                                       _cotizacion("AV-2", 100)]) == []


def test_un_avance_ilegible_cuenta_como_cero_y_no_rompe() -> None:
    """
    En la base hay avances que no son número. Un `float()` sin proteger tumbaría
    el script a mitad del lote, dejando la sincronización a medias.
    """
    pendientes = filas_a_sincronizar([_espejo("AV-1", "sin dato"), _espejo("AV-2", None)],
                                     [_cotizacion("AV-1", 100), _cotizacion("AV-2", 50)])

    assert {f["folio"] for f, _ in pendientes} == {"AV-1", "AV-2"}


def test_una_cotizacion_ilegible_no_arrastra_el_espejo_a_cero() -> None:
    assert filas_a_sincronizar([_espejo("AV-1", 50)], [_cotizacion("AV-1", "sin dato")]) == []


def test_el_lote_completo_se_resuelve_en_una_pasada() -> None:
    """Control de conjunto: mezcla de los cuatro casos a la vez."""
    espejo = [_espejo("AV-1", 0), _espejo("AV-2", 100), _espejo("AV-3", 100),
              _espejo("AV-4", 0, hoja="LUIS CARLOS"), _espejo("AV-5", 0)]
    cotizaciones = [_cotizacion("AV-1", 100), _cotizacion("AV-2", 100),
                    _cotizacion("AV-3", 50), _cotizacion("AV-4", 100)]

    pendientes = filas_a_sincronizar(espejo, cotizaciones)

    assert {f["folio"] for f, _ in pendientes} == {"AV-1"}
