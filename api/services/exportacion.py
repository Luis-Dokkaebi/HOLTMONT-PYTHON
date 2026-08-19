"""
Exportación de la selección del mapa a CSV y a XLSX, con la biblioteca estándar.

Por qué a mano y no con una librería
------------------------------------
`openpyxl` escribe XLSX en cuatro líneas, pero es dependencia **de desarrollo**
(`requirements-dev.txt`) y meterla en `api/requirements.txt` es justo lo que todo
el diseño de este módulo evita: el bundle de una función serverless de Vercel
tiene 250 MB y ya los reparten `fastapi`, `supabase`, `sqlalchemy` y `langchain`.

Un XLSX es un ZIP con cinco archivos XML dentro. `zipfile` y `xml` están en la
biblioteca estándar, así que el archivo se arma aquí y el runtime no gana ni una
dependencia. Son ~70 líneas y el formato lleva estable desde 2007.

Qué se exporta
--------------
Las mismas 10 columnas que pinta el mapa (`denue_repo.COLUMNAS_DEL_MAPA`) y
ninguna más. Un CSV con las 42 del DENUE no lo abre nadie, y el domicilio
completo no tiene por qué salir del servidor.
"""

from __future__ import annotations

import csv
import io
import zipfile
from typing import Any, Dict, Sequence
from xml.sax.saxutils import escape

from api.services.denue_repo import COLUMNAS_DEL_MAPA

# Encabezados legibles. La API habla en nombres de columna del INEGI; una hoja
# de cálculo que abre alguien de compras, no.
ENCABEZADOS: Dict[str, str] = {
    "id": "ID DENUE",
    "nom_estab": "NOMBRE",
    "nombre_act": "GIRO",
    "per_ocu": "PERSONAL",
    "telefono": "TELEFONO",
    "correoelec": "CORREO",
    "www": "SITIO WEB",
    "municipio": "ALCALDIA",
    "latitud": "LATITUD",
    "longitud": "LONGITUD",
}

NOMBRE_HOJA = "Prospectos"

# Fecha fija dentro del ZIP: dos exportaciones del mismo dato producen el mismo
# archivo, byte por byte. Con la hora del reloj, comparar dos descargas para ver
# si el catálogo cambió sería imposible.
FECHA_ZIP = (2026, 1, 1, 0, 0, 0)


def _fila_de(item: Dict[str, Any]) -> list:
    """Los valores en el orden de las columnas, con el nulo como celda vacía."""
    return [("" if item.get(col) is None else item[col]) for col in COLUMNAS_DEL_MAPA]


def a_csv(items: Sequence[Dict[str, Any]]) -> bytes:
    """
    CSV en UTF-8 **con BOM**.

    El BOM no es cosmético: sin él, Excel en Windows lee el archivo como
    ANSI y "Cuauhtémoc" llega como "CuauhtÃ©moc". Es el destino real de esta
    descarga, así que se paga el BOM.

    `\\r\\n` por la misma razón: es lo que espera Excel y lo que dice el RFC 4180.
    """
    buffer = io.StringIO()
    escritor = csv.writer(buffer, lineterminator="\r\n")
    escritor.writerow([ENCABEZADOS[c] for c in COLUMNAS_DEL_MAPA])
    escritor.writerows(_fila_de(item) for item in items)
    return buffer.getvalue().encode("utf-8-sig")


def _columna(indice: int) -> str:
    """`0 -> A`, `25 -> Z`, `26 -> AA`. Las 10 columnas caben en A..J."""
    letras = ""
    while True:
        indice, resto = divmod(indice, 26)
        letras = chr(ord("A") + resto) + letras
        if indice == 0:
            return letras
        indice -= 1


def _celda(referencia: str, valor: Any) -> str:
    """
    Una celda. Los números van como número y el resto como texto en línea.

    `inlineStr` en vez de la tabla de cadenas compartidas: ahorra un archivo XML
    entero y un índice, y aquí no hay repetición que compartir —cada fila es un
    negocio distinto—. Las coordenadas sí tienen que ser numéricas: como texto,
    ordenar por latitud en Excel daría un orden alfabético.
    """
    if isinstance(valor, (int, float)) and not isinstance(valor, bool):
        return f'<c r="{referencia}"><v>{valor}</v></c>'
    return (f'<c r="{referencia}" t="inlineStr"><is><t xml:space="preserve">'
            f'{escape(str(valor))}</t></is></c>')


def _hoja(items: Sequence[Dict[str, Any]]) -> str:
    filas = [[ENCABEZADOS[c] for c in COLUMNAS_DEL_MAPA]]
    filas.extend(_fila_de(item) for item in items)
    cuerpo = "".join(
        f'<row r="{numero}">'
        + "".join(_celda(f"{_columna(i)}{numero}", valor) for i, valor in enumerate(fila))
        + "</row>"
        for numero, fila in enumerate(filas, start=1)
    )
    return ('<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
            '<worksheet xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main">'
            f'<sheetData>{cuerpo}</sheetData></worksheet>')


_TIPOS = (
    '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
    '<Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types">'
    '<Default Extension="rels" ContentType="application/vnd.openxmlformats-package.relationships+xml"/>'
    '<Default Extension="xml" ContentType="application/xml"/>'
    '<Override PartName="/xl/workbook.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet.main+xml"/>'
    '<Override PartName="/xl/worksheets/sheet1.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.worksheet+xml"/>'
    '</Types>'
)

_RELS = (
    '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
    '<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">'
    '<Relationship Id="rId1" Target="xl/workbook.xml" '
    'Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/officeDocument"/>'
    '</Relationships>'
)

_LIBRO = (
    '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
    '<workbook xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main" '
    'xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships">'
    f'<sheets><sheet name="{NOMBRE_HOJA}" sheetId="1" r:id="rId1"/></sheets>'
    '</workbook>'
)

_RELS_LIBRO = (
    '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
    '<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">'
    '<Relationship Id="rId1" Target="worksheets/sheet1.xml" '
    'Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/worksheet"/>'
    '</Relationships>'
)


def a_xlsx(items: Sequence[Dict[str, Any]]) -> bytes:
    """El libro completo, en memoria. Una hoja, sin estilos y sin fórmulas."""
    partes = (
        ("[Content_Types].xml", _TIPOS),
        ("_rels/.rels", _RELS),
        ("xl/workbook.xml", _LIBRO),
        ("xl/_rels/workbook.xml.rels", _RELS_LIBRO),
        ("xl/worksheets/sheet1.xml", _hoja(items)),
    )
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w", zipfile.ZIP_DEFLATED) as libro:
        for nombre, contenido in partes:
            info = zipfile.ZipInfo(nombre, date_time=FECHA_ZIP)
            info.compress_type = zipfile.ZIP_DEFLATED
            libro.writestr(info, contenido)
    return buffer.getvalue()
