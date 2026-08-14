"""
Evidencia obligatoria para cerrar una actividad al 100 %.

Reporte del dueño (2026-08-14): los usuarios "tratan de cerrarlas al 100 % y no
se lo permiten, incluso si le colocan de nuevo todos los archivos".

`validateCompletionFiles` pedía `['ARCHIVO']` en el tracker de tareas y, además,
CORREO y CARPETA en **toda** tabla. Dos cosas fallaban a la vez:

* El tracker de tareas no tiene columna ARCHIVO: se llama CARPETA
  (`TASK_HEADER_MAP` en `api/services/sheets.py`, `carpeta` en la base). La
  exigencia que el código nombra no se aplicaba nunca.
* En su lugar quedaba una que nadie definió: subir el documento **dos veces**,
  una en CARPETA y otra en CORREO. Y CORREO no se persistió hasta el 2026-08-12
  (commit 3922b23), así que las actividades anteriores a esa fecha se quedaban
  sin poder cerrarse aunque su dueño volviera a adjuntar todo — el síntoma
  literal del reporte.

Regla nueva: **evidencia una vez**, en cualquiera de las columnas de archivo que
tenga la tabla. Los cinco entregables de una cotización se siguen pidiendo uno
por uno: son documentos distintos, no dos nombres del mismo archivo.

Se evalúa el código **real** de `index.html` con Node —la región que va de
`esAvanceCompleto` a `validateCompletionFiles`— porque una prueba de texto
pasaría aunque la validación estuviera al revés.
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

# Los encabezados que el backend devuelve hoy para un tracker de tareas
# (`TASK_HEADER_MAP`). Nótese que no hay ARCHIVO ni ESTATUS: son CARPETA y
# STATUS, y de ahí salía el defecto.
ENCABEZADOS_TRACKER = ["FOLIO", "ALTA", "FECHA", "CONCEPTO", "INVOLUCRADOS",
                       "AVANCE %", "CORREO", "CARPETA", "STATUS",
                       "CUMPLIMIENTO", "COMENTARIOS"]

ENCABEZADOS_VENTAS = ["FOLIO", "CLIENTE", "CONCEPTO", "VENDEDOR", "AVANCE",
                      "ESTATUS", "INFO CLIENTE", "F2", "COTIZACION",
                      "TIMELINE", "LAYOUT", "CORREO", "CARPETA"]


def _region() -> str:
    with open(INDEX, encoding="utf-8") as fh:
        fuente = fh.read()
    patron = (r"const esAvanceCompleto = \(valor\) => \{.*?"
              r"const validateCompletionFiles = \(row, headers\) => \{.*?\n      \};")
    m = re.search(patron, fuente, re.S)
    assert m, "no se encontró la región de validación de evidencia en index.html"
    return m.group(0)


def _validar(row: dict, headers: list) -> dict:
    guion = f"""
        {_region()}
        console.log(JSON.stringify(
            validateCompletionFiles({json.dumps(row)}, {json.dumps(headers)})));
    """
    salida = subprocess.run(["node", "-e", guion], capture_output=True,
                            text=True, timeout=30, check=False)
    assert salida.returncode == 0, f"node falló: {salida.stderr}"
    return json.loads(salida.stdout)


def _avance_completo(valor) -> bool:
    guion = f"""
        {_region()}
        console.log(JSON.stringify(esAvanceCompleto({json.dumps(valor)})));
    """
    salida = subprocess.run(["node", "-e", guion], capture_output=True,
                            text=True, timeout=30, check=False)
    assert salida.returncode == 0, f"node falló: {salida.stderr}"
    return json.loads(salida.stdout)


def _fila(**campos) -> dict:
    base = {h: "" for h in ENCABEZADOS_TRACKER}
    base.update({"FOLIO": "MG-0001", "CONCEPTO": "Cambiar tablero"})
    base.update(campos)
    return base


# ---------------------------------------------------------------------------
# 1. El defecto reportado: no se podía cerrar aunque hubiera archivo
# ---------------------------------------------------------------------------

def test_con_el_documento_en_carpeta_se_puede_cerrar_al_100():
    """El caso del reporte: hay evidencia, la validación tiene que dejar pasar."""
    fila = _fila(**{"AVANCE %": "100", "CARPETA": "https://storage/evidencia.pdf"})
    assert _validar(fila, ENCABEZADOS_TRACKER) == {"valid": True}


def test_con_el_documento_solo_en_correo_tambien_se_puede_cerrar():
    """CORREO y CARPETA son las dos nubes de la misma fila, no dos requisitos."""
    fila = _fila(**{"AVANCE %": "100", "CORREO": "https://storage/acuse.pdf"})
    assert _validar(fila, ENCABEZADOS_TRACKER) == {"valid": True}


def test_sin_ningun_archivo_sigue_sin_poder_cerrarse():
    """La exigencia de evidencia no se relaja: cerrar sin nada adjunto se bloquea."""
    resultado = _validar(_fila(**{"AVANCE %": "100"}), ENCABEZADOS_TRACKER)
    assert resultado["valid"] is False
    assert "CARPETA" in resultado["missing"] and "CORREO" in resultado["missing"], (
        "el aviso tiene que decir en qué columnas se acepta el documento")


def test_cumplimiento_si_tambien_exige_evidencia():
    resultado = _validar(_fila(CUMPLIMIENTO="SI"), ENCABEZADOS_TRACKER)
    assert resultado["valid"] is False


def test_una_actividad_a_medias_se_guarda_sin_archivos():
    assert _validar(_fila(**{"AVANCE %": "40"}), ENCABEZADOS_TRACKER) == {"valid": True}


# ---------------------------------------------------------------------------
# 2. El "1" que no es 100 % (AGENTS.md §4)
# ---------------------------------------------------------------------------

def test_una_tarea_al_1_por_ciento_no_se_toma_por_cerrada():
    """
    `"1"` es 1 %, no 100 % (AGENTS.md §4). La expresión vieja
    —`parseFloat(v) === 1 && !v.includes('%')`— lo daba por cerrado sobre el
    texto que manda el backend, y entonces pedía evidencia para guardar un 1 %.
    """
    assert _validar(_fila(**{"AVANCE %": "1"}), ENCABEZADOS_TRACKER) == {"valid": True}


@pytest.mark.parametrize("valor,completo", [
    (1, True),          # número nativo: celda con formato de porcentaje
    (1.0, True),
    (100, True),
    ("100", True),
    ("100%", True),
    ("100,0", True),
    ("1", False),
    ("1.0", False),
    ("40", False),
    ("", False),
    (None, False),
])
def test_la_lectura_del_avance_coincide_con_la_del_backend(valor, completo):
    """Misma tabla que `test_tracker_rules.test_evaluacion_de_avance`."""
    assert _avance_completo(valor) is completo


# ---------------------------------------------------------------------------
# 3. Las cotizaciones siguen pidiendo sus cinco entregables
# ---------------------------------------------------------------------------

def _fila_venta(**campos) -> dict:
    base = {h: "" for h in ENCABEZADOS_VENTAS}
    base.update({"FOLIO": "AV-0001", "CONCEPTO": "COTIZAR NAVE"})
    base.update(campos)
    return base


def test_una_cotizacion_al_100_sin_layout_no_se_cierra():
    fila = _fila_venta(**{
        "AVANCE": "100", "INFO CLIENTE": "u", "F2": "u", "COTIZACION": "u",
        "TIMELINE": "u", "CARPETA": "u",
    })
    resultado = _validar(fila, ENCABEZADOS_VENTAS)
    assert resultado == {"valid": False, "missing": "LAYOUT"}


def test_una_cotizacion_con_sus_cinco_documentos_se_cierra():
    fila = _fila_venta(**{
        "AVANCE": "100", "INFO CLIENTE": "u", "F2": "u", "COTIZACION": "u",
        "TIMELINE": "u", "LAYOUT": "u", "CARPETA": "u",
    })
    assert _validar(fila, ENCABEZADOS_VENTAS) == {"valid": True}
