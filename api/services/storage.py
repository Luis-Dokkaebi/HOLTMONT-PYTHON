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
import hashlib
import os
import re
import unicodedata
from datetime import datetime
from typing import Any, Dict, Optional, Tuple

BUCKET_ENV = "SUPABASE_BUCKET"
BUCKET_POR_DEFECTO = "archivos"

# Bucket dedicado a evidencia de tickets de bug. Deliberadamente distinto de
# `BUCKET_ENV`: ese es público y admite `upsert`; este es privado y no admite
# ninguna de las dos cosas (docs/DDL_PENDIENTE.sql §5 — sin política de
# UPDATE/DELETE, Postgres deniega por default).
BUCKET_EVIDENCIA_ENV = "SUPABASE_BUCKET_TICKETS"
BUCKET_EVIDENCIA_POR_DEFECTO = "ticket-evidencia"

# Mismo orden de magnitud que `MAX_UPLOAD_BYTES` de `index.html` (35 MB) para
# los adjuntos del tracker; el video de un bug suele pesar más que una foto.
MAX_BYTES_EVIDENCIA = 50 * 1024 * 1024

MIME_EVIDENCIA_PERMITIDOS = frozenset(
    {"video/mp4", "video/webm", "image/png", "image/jpeg"}
)

# Igual que el original: sin tipo declarado, octet-stream. Pasa con .dwg y .zip,
# que el navegador no sabe etiquetar.
MIME_POR_DEFECTO = "application/octet-stream"

MESES = ["ENERO", "FEBRERO", "MARZO", "ABRIL", "MAYO", "JUNIO", "JULIO",
         "AGOSTO", "SEPTIEMBRE", "OCTUBRE", "NOVIEMBRE", "DICIEMBRE"]


def bucket() -> str:
    return os.environ.get(BUCKET_ENV, "").strip() or BUCKET_POR_DEFECTO


def bucket_evidencia() -> str:
    return os.environ.get(BUCKET_EVIDENCIA_ENV, "").strip() or BUCKET_EVIDENCIA_POR_DEFECTO


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


def ruta_de_evidencia(folio: Any, nombre: Any, fecha: Any = None) -> str:
    """
    `AÑO/MES/<folio>/archivo-<timestamp>`, mismo patrón que `ruta_de_archivo`
    con el folio del ticket en vez del cliente: aquí no hay banco de
    cotizaciones, hay un caso. El timestamp en el nombre es lo que hace que
    dos subidas nunca compartan ruta, aun para el mismo ticket.
    """
    momento = fecha if isinstance(fecha, datetime) else datetime.now()
    partes = [str(momento.year), MESES[momento.month - 1], limpiar_segmento(folio, "SIN_FOLIO")]
    limpio = limpiar_segmento(nombre, "evidencia")
    sello = int(momento.timestamp() * 1000)
    raiz, extension = os.path.splitext(limpio)
    partes.append(f"{raiz}-{sello}{extension}")
    return "/".join(partes)


def subir_evidencia_ticket(folio: Any, data: Any, tipo: Any = None, nombre: Any = None) -> Dict[str, Any]:
    """
    Sube un adjunto de un ticket de bug y devuelve
    `{success, fileUrl, path, sha256, mime}`.

    Tres diferencias deliberadas frente a `subir()`:

    * bucket propio y privado (`bucket_evidencia()`), no el `archivos`
      público que ya usan el tracker y el banco;
    * whitelist de MIME y tope de tamaño, porque esto es evidencia de un
      reporte, no cualquier documento;
    * `upsert: "false"` explícito y el hash del contenido devuelto: la
      inmutabilidad que promete el ticket depende de que esta función jamás
      pise un objeto existente, y el `sha256` es lo que permite verificar
      después que nadie lo hizo por otra vía.

    La otra mitad de esa garantía —que nadie pueda editar ni borrar el
    objeto una vez subido— la da la política de Storage
    (docs/DDL_PENDIENTE.sql §5), no este código: aquí solo se asegura que la
    propia plataforma nunca ofrezca el camino para intentarlo.
    """
    from api.services.supabase_manager import sb_manager

    if not sb_manager.is_configured:
        return {"success": False,
                "message": "Supabase no está configurado: la evidencia NO se subió."}

    try:
        contenido, mime_detectado = decodificar_data_url(data)
    except ValueError as exc:
        return {"success": False, "message": str(exc)}

    if not contenido:
        return {"success": False, "message": "El archivo llegó vacío."}

    if len(contenido) > MAX_BYTES_EVIDENCIA:
        return {"success": False,
                "message": f"El archivo pesa {len(contenido)} bytes; "
                           f"el máximo permitido es {MAX_BYTES_EVIDENCIA}."}

    mime = str(tipo or "").strip() or mime_detectado or MIME_POR_DEFECTO
    if mime not in MIME_EVIDENCIA_PERMITIDOS:
        permitidos = ", ".join(sorted(MIME_EVIDENCIA_PERMITIDOS))
        return {"success": False,
                "message": f"Tipo {mime!r} no permitido para evidencia. Solo: {permitidos}."}

    ruta = ruta_de_evidencia(folio, nombre)
    sha256 = hashlib.sha256(contenido).hexdigest()

    try:
        almacen = sb_manager.client.storage.from_(bucket_evidencia())
        almacen.upload(ruta, contenido, {"content-type": mime, "upsert": "false"})
        url = almacen.get_public_url(ruta)
    except Exception as exc:  # noqa: BLE001
        return {"success": False, "message": f"No se pudo subir la evidencia: {exc}"}

    return {"success": True, "fileUrl": url, "path": ruta, "sha256": sha256, "mime": mime}


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
