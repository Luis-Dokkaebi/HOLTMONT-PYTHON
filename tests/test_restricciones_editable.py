"""
La columna «Restricciones y Comentarios» se puede escribir después del alta.

El permiso de campo vive en `isFieldEditable` de `index.html`. Para el rol
`TONITA` (la cuenta `ANTONIA_VENTAS`) funciona con una lista blanca: mientras la
fila no tiene folio todo es editable, y en cuanto el backend le pone folio solo
sobreviven los encabezados que aparecen en esa lista.

El defecto que cubre esta prueba: la lista se escribió con los rótulos que ve el
usuario, y esta columna **no se llama como se rotula**. La API la rinde como
`RESTRICCIONES` (`sheets.TASK_HEADER_MAP`) y es `getHeaderLabel` quien la pinta
como `Restricciones y Comentarios` (`ETIQUETAS_DE_COLUMNA`). La lista blanca
traía `COMENTARIOS` —que casaba con el rótulo, no con el encabezado— así que en
cuanto la actividad quedaba asignada la celda se volvía de solo lectura y Toñita
no podía anotar la restricción, que es justo cuando aparece.

Se comprueba evaluando el `isFieldEditable` real con Node, igual que
`test_etiquetas_columnas.py`: una prueba de texto sobre el archivo pasaría
aunque la comparación siguiera sin casar.
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

# Una fila ya dada de alta: el backend le puso folio, así que la lista blanca
# del rol es lo único que decide.
FILA_ASIGNADA = {"FOLIO": "AP-0042", "ID": "AP-0042", "ESTATUS": "ASIGNADO"}
FILA_NUEVA = {"_isNew": True}


def _fuente() -> str:
    with open(INDEX, encoding="utf-8") as fh:
        return fh.read()


def _bloque_de_permisos() -> str:
    """`isFieldEditable` y el mínimo para evaluarla fuera de Vue."""
    m = re.search(r"const isFieldEditable = \(h, row\) => \{.*?\n      \};",
                  _fuente(), re.S)
    assert m, "no se encontró `isFieldEditable` en index.html"
    return "const currentRole = { value: '' };\n" + m.group(0)


def _es_editable(rol: str, encabezado: str, fila: dict) -> bool:
    guion = f"""
        {_bloque_de_permisos()}
        currentRole.value = {json.dumps(rol)};
        console.log(JSON.stringify(
            isFieldEditable({json.dumps(encabezado)}, {json.dumps(fila)})
        ));
    """
    salida = subprocess.run(["node", "-e", guion], capture_output=True,
                            text=True, timeout=30, check=False)
    assert salida.returncode == 0, f"node falló: {salida.stderr}"
    return bool(json.loads(salida.stdout))


@pytest.mark.skipif(shutil.which("node") is None, reason="node no está instalado")
def test_tonita_escribe_restricciones_en_una_actividad_ya_asignada() -> None:
    """El defecto reportado: la celda se bloqueaba justo al asignar."""
    assert _es_editable("TONITA", "RESTRICCIONES", FILA_ASIGNADA), (
        "la columna RESTRICCIONES quedó de solo lectura en una fila con folio; "
        "es la celda donde se anota la restricción de la actividad asignada"
    )


@pytest.mark.skipif(shutil.which("node") is None, reason="node no está instalado")
def test_el_encabezado_que_se_verifica_es_el_que_rinde_la_api() -> None:
    """
    La prueba de arriba solo vale si `RESTRICCIONES` es de verdad el encabezado
    que llega al navegador. Se comprueba contra el mapa del backend en vez de
    darlo por supuesto: si mañana la API lo renombra, salta aquí.
    """
    from api.services.sheets import TASK_HEADER_MAP

    assert ("RESTRICCIONES", "restricciones") in TASK_HEADER_MAP


@pytest.mark.skipif(shutil.which("node") is None, reason="node no está instalado")
def test_la_fila_sin_folio_sigue_siendo_editable_entera() -> None:
    """Alta: mientras no hay folio no hay candado. No debe cambiar."""
    assert _es_editable("TONITA", "RESTRICCIONES", FILA_NUEVA)
    assert _es_editable("TONITA", "CONCEPTO", FILA_NUEVA)


@pytest.mark.skipif(shutil.which("node") is None, reason="node no está instalado")
@pytest.mark.parametrize("encabezado", ["CONCEPTO", "FOLIO", "CLASIFICACION"])
def test_el_candado_del_historial_sigue_puesto(encabezado: str) -> None:
    """
    El contrapeso: abrir RESTRICCIONES no puede abrirlo todo.

    Sin esto, un `return true` al principio de la rama TONITA pasaría la prueba
    del defecto y borraría el permiso de campo entero.
    """
    assert not _es_editable("TONITA", encabezado, FILA_ASIGNADA), (
        f"{encabezado} quedó editable en una fila ya dada de alta: el candado "
        "sobre el historial se abrió de más"
    )


@pytest.mark.skipif(shutil.which("node") is None, reason="node no está instalado")
def test_los_roles_restringidos_no_ganan_permisos() -> None:
    """
    El cambio es del tracker de Toñita. Los siete usuarios restringidos
    (`ANGEL_USER` y compañía) tienen su propia lista blanca y no se tocó.
    """
    assert not _es_editable("ANGEL_USER", "RESTRICCIONES", FILA_ASIGNADA)
