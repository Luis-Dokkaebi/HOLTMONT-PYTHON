"""
Las columnas del tracker, en el orden y con los nombres del original.

La referencia es la vista `STAFF_TRACKER` de Apps Script, que el equipo usa a
diario. La migración debe reproducirla sin que se note el cambio de plataforma:
mismas columnas, mismo orden, mismos rótulos.

Cubre dos cosas que se rompen por separado:

  1. **Que cada encabezado llegue a su columna** (`ALIAS_DE_HOJA`). Es lo que
     gobierna la escritura: `columnas_desde_hoja` descarta lo que no reconoce,
     así que un alias que falta no da error — guarda la fila sin ese campo.
  2. **Que la API las exponga en el orden de la hoja** (`TASK_HEADER_MAP`).

`ALTA` es el **área**: así se rotula la columna en la vista del original y así lo
declara `CODIGO.js:2228` (`'ALTA': ['AREA', 'DEPARTAMENTO', 'ESPECIALIDAD',
'ALTA']`). Estaba como alias de `fecha_alta`, de modo que una fila sin fecha
guardaba el nombre del departamento en un campo `date`. Los ocho sitios del
original que hacen `t['FECHA'] || t['ALTA']` son ese mismo defecto: leen el área
como fecha cuando falta la fecha, y no se replican aquí.

`correo` fue la excepción hasta el 2026-08-12: aparecía en la vista pero no
llevaba alias, y estaba en `SOLO_LECTURA`. Ya no. Contiene enlaces de Drive, no
direcciones, y la tabla deja subir documentos ahí, así que sin alias cada
guardado borraba el archivo recién subido (`tests/test_documento_en_correo.py`).
Ahora las 18 columnas de la vista se leen y se escriben.
"""

from __future__ import annotations

from typing import List, Tuple

import pytest

from backend.schemas.hoja import clave_encabezado, columnas_desde_hoja
from backend.schemas.task import (
    ALIAS_DE_HOJA,
    COLUMNAS_TASKS,
    INDICE_ALIAS,
    SOLO_LECTURA,
)

# Las 18 columnas de la vista del original, en su orden.
ORDEN_DE_LA_VISTA: List[Tuple[str, str]] = [
    ("Folio", "folio"),
    ("Alta", "departamento"),
    ("Fecha", "fecha_alta"),
    ("Hora", "hora_alta"),
    ("Clasi", "clasificacion"),
    ("Concepto", "concepto"),
    ("Involucrados", "assignee_raw"),
    ("Avance %", "avance"),
    ("Fec. Est. Fin", "fecha_estimada_fin"),
    ("Hr. Est. Fin", "hora_estimada_fin"),
    ("Reloj", "reloj"),
    ("Restricciones y Comentarios", "restricciones"),
    ("Prioridades", "prioridad"),
    ("Riesgos", "riesgos"),
    ("Fecha respuesta", "fecha_respuesta"),
    ("Correo", "correo"),
    ("Carpeta", "carpeta"),
    ("Status", "status"),
]

# Las que además deben poder escribirse desde una fila con forma de hoja.
ESCRIBIBLES = [(h, c) for h, c in ORDEN_DE_LA_VISTA if c not in SOLO_LECTURA]


@pytest.mark.parametrize(("encabezado", "columna"), ESCRIBIBLES)
def test_cada_encabezado_de_la_vista_llega_a_su_columna(encabezado: str,
                                                        columna: str) -> None:
    resuelto = INDICE_ALIAS.get(clave_encabezado(encabezado))
    assert resuelto == columna, (
        f"el encabezado {encabezado!r} se resolvió a {resuelto!r} y debería ser "
        f"{columna!r}; con el alias mal, su valor se pierde al guardar"
    )


def test_una_fila_de_la_hoja_no_pierde_ninguna_columna() -> None:
    """El control de conjunto: dice cuántas se pierden, no solo cuál falla."""
    fila = {h: f"valor-{i}" for i, (h, _) in enumerate(ESCRIBIBLES)}
    columnas = columnas_desde_hoja(fila, INDICE_ALIAS)

    perdidas = {c for _, c in ESCRIBIBLES} - set(columnas)
    assert perdidas == set(), f"se perdieron al guardar: {sorted(perdidas)}"


def test_alta_es_el_area_y_no_una_fecha() -> None:
    """
    `CODIGO.js:2228` — `'ALTA': ['AREA', 'DEPARTAMENTO', 'ESPECIALIDAD', 'ALTA']`.

    Se comprueba en los dos sentidos: que resuelva a `departamento` y que
    ninguna columna de fecha la reclame. Si las dos la declaran, cuál gana
    depende del orden del diccionario, que es un sitio pésimo donde dejar una
    regla de negocio.
    """
    assert INDICE_ALIAS[clave_encabezado("ALTA")] == "departamento"

    for columna in ("fecha_alta", "fecha_estimada_fin", "fecha_respuesta"):
        claves = {clave_encabezado(a) for a in ALIAS_DE_HOJA.get(columna, [])}
        assert clave_encabezado("ALTA") not in claves, (
            f"`{columna}` reclama el encabezado ALTA, que es el área"
        )

    # `FECHA ALTA` y `FECHA DE ALTA` sí son la fecha: la ambigüedad era solo con
    # `ALTA` a secas.
    assert INDICE_ALIAS[clave_encabezado("FECHA ALTA")] == "fecha_alta"
    assert INDICE_ALIAS[clave_encabezado("FECHA DE ALTA")] == "fecha_alta"


def test_toda_columna_de_negocio_se_puede_escribir_desde_la_hoja() -> None:
    """
    Una columna sin alias no da error: simplemente nunca se escribe.

    Se contrasta contra `SOLO_LECTURA`, que es donde se declara qué queda fuera
    a propósito. Así una columna nueva sin alias salta aquí, en vez de quedarse
    vacía para siempre sin que nadie lo note.
    """
    sin_alias = [c for c in COLUMNAS_TASKS
                 if c not in ALIAS_DE_HOJA and c not in SOLO_LECTURA]

    assert sin_alias == [], (
        f"columnas de negocio sin alias de hoja (no se pueden escribir): {sin_alias}"
    )


def test_la_api_expone_las_columnas_en_el_orden_de_la_vista() -> None:
    """
    `TASK_HEADER_MAP` fija el orden que ve el usuario.

    El orden importa más de lo que parece: el equipo lleva años leyendo esta
    tabla de izquierda a derecha, y cambiarlo es lo que hace que un sistema
    portado «se sienta» distinto aunque traiga los mismos datos.
    """
    from api.services.sheets import TASK_HEADER_MAP

    curadas = [col for _, col in TASK_HEADER_MAP]
    esperadas = [col for _, col in ORDEN_DE_LA_VISTA]

    assert curadas[:len(esperadas)] == esperadas, (
        f"el orden no coincide con la vista del original.\n"
        f"  esperado: {esperadas}\n"
        f"  obtenido: {curadas[:len(esperadas)]}"
    )
