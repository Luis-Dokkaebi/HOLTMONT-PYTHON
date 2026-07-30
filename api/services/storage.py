"""
Almacenamiento de archivos en Supabase Storage.

Sustituye a `uploadFileToDrive` (DriveApp) y al archivado
`[Año]/[Mes]/[Cliente]` que el original hacía con carpetas de Drive
(`getBankRootFolder`, `getOrCreateFolder`, `archiveFile`, `processQuoteRow`).

Era el último stub del adaptador y el de mayor impacto: bloqueaba los adjuntos
del tracker, del PPC y del banco de información. Antes de la Fase 0 devolvía
una URL inventada (`http://mock.url/file`) que se guardaba en la base como si
el archivo existiera; después pasó a fallar de forma visible, que es correcto
pero sigue siendo una función que falta.

**En Storage no hay carpetas.** La jerarquía de Drive se traduce a prefijos de
la ruta del objeto: `2026/MARZO/ACME INDUSTRIAL/cotizacion.pdf`. El resultado
para el usuario es el mismo —los objetos se listan por prefijo— y no hay que
crear nada antes de subir.
"""

from __future__ import annotations

import base64
import os
import re
import unicodedata
from datetime import datetime
from typing import Any, Dict, Optional, Tuple

BUCKET_ENV = "SUPABASE_BUCKET"
BUCKET_POR_DEFECTO = "archivos"

# Igual que el original: sin tipo declarado, octet-stream. Pasa con .dwg y .zip,
# que el navegador no sabe etiquetar.
MIME_POR_DEFECTO = "application/octet-stream"

MESES = ["ENERO", "FEBRERO", "MARZO", "ABRIL", "MAYO", "JUNIO", "JULIO",
         "AGOSTO", "SEPTIEMBRE", "OCTUBRE", "NOVIEMBRE", "DICIEMBRE"]


def bucket() -> str:
    return os.environ.get(BUCKET_ENV, "").strip() or BUCKET_POR_DEFECTO


def decodificar_data_url(data: Any) -> Tuple[bytes, Optional[str]]:
    """
    Bytes y tipo MIME de un data URL (`data:image/png;base64,iVBOR...`).

    El frontend usa `FileReader.readAsDataURL`, así que siempre llega con
    prefijo; se acepta también base64 pelado por si algún llamador lo manda así.
    """
    texto = str(data or "")
    if not texto:
        raise ValueError("No llegó contenido del archivo.")

    mime = None
    if texto.startswith("data:"):
        cabecera, _, cuerpo = texto.partition(",")
        if not cuerpo:
            raise ValueError("Data URL sin contenido tras la coma.")
        mime = cabecera[5:].split(";")[0] or None
        texto = cuerpo

    try:
        return base64.b64decode(texto, validate=False), mime
    except Exception as exc:  # noqa: BLE001
        raise ValueError(f"El contenido no es base64 válido: {exc}") from exc


def limpiar_segmento(valor: Any, respaldo: str = "SIN_NOMBRE") -> str:
    """
    Segmento de ruta seguro para Storage.

    Storage acepta un subconjunto de caracteres en las claves; los acentos y los
    signos rompen la URL pública. Se transliteran en vez de eliminarse para que
    "DISEÑO" no acabe como "DISEO".
    """
    texto = str(valor or "").strip()
    if not texto:
        return respaldo
    texto = unicodedata.normalize("NFKD", texto).encode("ascii", "ignore").decode()
    texto = re.sub(r"[^A-Za-z0-9._ -]", "", texto).strip()
    texto = re.sub(r"\s+", " ", texto)
    return texto or respaldo


def ruta_de_archivo(nombre: Any, cliente: Any = None, fecha: Any = None) -> str:
    """
    Ruta del objeto. Con cliente, la del banco: `AÑO/MES/CLIENTE/archivo`.

    Sin cliente cae en `AÑO/MES/archivo`, que es el equivalente de subir a la
    carpeta raíz de uploads del original.
    """
    momento = fecha if isinstance(fecha, datetime) else None
    if momento is None:
        from api.services.tracker_rules import parse_sheet_date

        momento = parse_sheet_date(fecha) or datetime.now()

    partes = [str(momento.year), MESES[momento.month - 1]]
    if cliente:
        partes.append(limpiar_segmento(cliente, "SIN_CLIENTE"))

    limpio = limpiar_segmento(nombre, "archivo")
    # Marca de tiempo para no pisar un archivo del mismo nombre: en Drive dos
    # archivos homónimos conviven, en Storage el segundo sobreescribiría al
    # primero.
    sello = int(momento.timestamp() * 1000)
    raiz, extension = os.path.splitext(limpio)
    partes.append(f"{raiz}-{sello}{extension}")
    return "/".join(partes)


def subir(data: Any, tipo: Any = None, nombre: Any = None,
          cliente: Any = None, fecha: Any = None) -> Dict[str, Any]:
    """
    Sube el archivo y devuelve `{success, fileUrl}` — la forma que espera el
    frontend de `uploadFileToDrive`.

    El original publicaba el archivo con `ANYONE_WITH_LINK`, así que el bucket
    equivalente debe ser público; si es privado, `get_public_url` devuelve una
    URL que no resuelve. Queda anotado en `docs/DDL_PENDIENTE.sql`.
    """
    from api.services.supabase_manager import sb_manager

    if not sb_manager.is_configured:
        return {"success": False,
                "message": "Supabase no está configurado: el archivo NO se subió."}

    try:
        contenido, mime_detectado = decodificar_data_url(data)
    except ValueError as exc:
        return {"success": False, "message": str(exc)}

    if not contenido:
        return {"success": False, "message": "El archivo llegó vacío."}

    mime = str(tipo or "").strip() or mime_detectado or MIME_POR_DEFECTO
    ruta = ruta_de_archivo(nombre, cliente, fecha)

    try:
        almacen = sb_manager.client.storage.from_(bucket())
        almacen.upload(ruta, contenido, {"content-type": mime, "upsert": "true"})
        url = almacen.get_public_url(ruta)
    except Exception as exc:  # noqa: BLE001
        # Sin URL falsa: el llamador tiene que saber que no se guardó.
        return {"success": False, "message": f"No se pudo subir a Storage: {exc}"}

    return {"success": True, "fileUrl": url, "path": ruta}


def archivar_cotizacion(file_url: Any, cliente: Any, fecha: Any = None) -> Dict[str, Any]:
    """
    Reubica un archivo ya subido en `AÑO/MES/CLIENTE/`.

    Equivalente de `archiveFile` + `processQuoteRow`. En Drive era mover el
    archivo entre carpetas; aquí es un `move` de la clave del objeto, que es la
    misma operación sobre el mismo dato.

    Si la URL no es de este bucket se devuelve `success: False` sin tocar nada,
    igual que el original ignoraba lo que no fuera una URL de Drive.
    """
    from api.services.supabase_manager import sb_manager

    if not sb_manager.is_configured:
        return {"success": False, "message": "Supabase no está configurado."}

    ruta_actual = _ruta_desde_url(file_url)
    if not ruta_actual:
        return {"success": False, "message": "La URL no corresponde a este bucket."}

    destino = ruta_de_archivo(os.path.basename(ruta_actual), cliente, fecha)
    if ruta_actual == destino:
        return {"success": True, "message": "Ya estaba archivado."}

    try:
        almacen = sb_manager.client.storage.from_(bucket())
        almacen.move(ruta_actual, destino)
        url = almacen.get_public_url(destino)
    except Exception as exc:  # noqa: BLE001
        return {"success": False, "message": f"No se pudo archivar: {exc}"}

    return {"success": True, "fileUrl": url, "path": destino, "message": "Archivado."}


def _ruta_desde_url(file_url: Any) -> Optional[str]:
    """
    Clave del objeto a partir de su URL pública.

    Formato de Supabase: `.../storage/v1/object/public/<bucket>/<ruta>`.
    """
    texto = str(file_url or "")
    marca = f"/object/public/{bucket()}/"
    if marca not in texto:
        return None
    ruta = texto.split(marca, 1)[1].split("?")[0]
    return ruta or None
