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
from urllib.parse import unquote

BUCKET_ENV = "SUPABASE_BUCKET"
BUCKET_POR_DEFECTO = "archivos"

# Bucket dedicado a evidencia de tickets de bug. Deliberadamente distinto de
# `BUCKET_ENV`: ese es público y admite `upsert`; este es privado y no admite
# ninguna de las dos cosas (docs/DDL_PENDIENTE.sql §5 — sin política de
# UPDATE/DELETE, Postgres deniega por default).
BUCKET_EVIDENCIA_ENV = "SUPABASE_BUCKET_TICKETS"
BUCKET_EVIDENCIA_POR_DEFECTO = "ticket-evidencia"

# Cuánto vive la URL con la que el navegador abre una evidencia.
#
# Reporte del 2026-08-24: al abrir "Evidencia 1" desde el panel de tickets el
# navegador mostraba, en vez de la imagen,
# `{"statusCode":"404","error":"Bucket not found","code":"NoSuchBucket"}`.
#
# La causa NO era que faltara el bucket: es que la evidencia se guardaba con la
# URL que devuelve `get_public_url`, y ese endpoint
# (`/storage/v1/object/public/<bucket>/...`) solo sirve buckets **públicos**.
# `ticket-evidencia` es privado a propósito (docs/DDL_PENDIENTE.sql §5), y para
# un bucket que existe pero no es público Storage responde exactamente ese
# `NoSuchBucket` — el mismo cuerpo que si no existiera, de ahí la confusión.
#
# El arreglo no es hacer público el bucket (eso publicaría la evidencia de
# todos los reportes a quien adivine la ruta) sino leerla con URL firmada, que
# se emite en el momento de abrir el archivo y caduca sola. Cinco minutos
# alcanzan para abrir o descargar el adjunto y no dejan un enlace vivo si la
# URL se reenvía por chat.
SEGUNDOS_URL_FIRMADA = 300

# Mismo orden de magnitud que `MAX_UPLOAD_BYTES` de `index.html` (35 MB) para
# los adjuntos del tracker; el video de un bug suele pesar más que una foto.
MAX_BYTES_EVIDENCIA = 50 * 1024 * 1024

# Lo que de verdad cabe por `/api/legacy/upload`.
#
# Reporte BUG-0009 (2026-08-18): "no me deja cerrar tareas que capture ni cargar
# archivos pesados". La causa no está en este módulo sino en el camino: el
# archivo viaja como data URL dentro de un JSON, y ese JSON es el cuerpo de una
# función serverless de Vercel, que rechaza cualquier petición de más de 4.5 MB
# antes de que el código llegue a ejecutarse. Base64 infla 4/3, así que por esa
# ruta no pasa un archivo de más de ~3.3 MB por mucho que `index.html`
# anunciara 35 MB.
#
# El tope se declara aquí —y se comprueba— para que el rechazo tenga un mensaje
# que diga qué hacer, en vez de un 413 de la plataforma sin cuerpo JSON.
LIMITE_CUERPO_FUNCION = 4_500_000
MAX_BYTES_SUBIDA_JSON = 3 * 1024 * 1024

# Lo que cabe por la ruta directa (URL firmada): el archivo va del navegador a
# Storage sin pasar por la función, así que el tope vuelve a ser el del
# producto y no el del sobre.
MAX_BYTES_SUBIDA_DIRECTA = 35 * 1024 * 1024

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
    * `upsert: "false"` explícito y el hash del contenido devuelto.

    Sobre el alcance real, medido contra el proyecto el 2026-08-13: las
    políticas de Storage impiden alterar la evidencia con la clave `anon`
    —la única que se publica en el navegador— pero **no** con la de servicio,
    que tiene BYPASSRLS y sobrescribe (`PUT` con `x-upsert`) y borra sin
    problema. Storage no ofrece object-lock, así que no existe configuración
    que lo impida.

    De ahí que el `sha256` sea la pieza que importa: no impide la alteración,
    la vuelve **detectable**. Ver `verificar_evidencia`.
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
    except Exception as exc:
        return {"success": False, "message": f"No se pudo subir la evidencia: {exc}"}

    # `fileUrl` se sigue devolviendo con la forma pública porque es lo que hay
    # guardado en los tickets viejos y lo que `verificar_evidencia` sabe leer:
    # sirve de identificador estable del objeto, **no** de enlace para abrirlo.
    # Para abrirlo está `url_firmada_evidencia`, y `path` es lo que hace que la
    # lectura no dependa de saber descomponer una URL.
    return {"success": True, "fileUrl": url, "path": ruta, "sha256": sha256, "mime": mime}


def verificar_evidencia(file_url: Any, sha256_esperado: Any) -> Dict[str, Any]:
    """
    ¿El archivo que hay hoy en Storage es el que se subió?

    Descarga el objeto y compara su hash con el que se guardó en
    `bug_tickets.evidencia[].sha256` al momento de subirlo. Devuelve
    `{estado, ...}` con uno de tres veredictos:

    * `intacta`     — el hash coincide;
    * `alterada`    — el archivo existe pero su hash cambió;
    * `desaparecida`— el objeto ya no está.

    Esto es lo que hace útil al `sha256`. Las políticas de Storage impiden que
    la evidencia se toque desde el navegador, pero no desde la clave de
    servicio (medido: `PUT` con `x-upsert` y `DELETE` pasan). No pudiendo
    impedir la alteración, lo que queda es poder demostrarla — y una promesa
    de integridad que nadie puede comprobar no vale nada.
    """
    from api.services.supabase_manager import sb_manager

    esperado = str(sha256_esperado or "").strip().lower()
    if not esperado:
        return {"estado": "sin_hash",
                "mensaje": "La evidencia se guardó sin sha256: no hay contra qué comparar."}

    if not sb_manager.is_configured:
        return {"estado": "indeterminado", "mensaje": "Supabase no está configurado."}

    ruta = _ruta_de_evidencia(file_url)
    if not ruta:
        return {"estado": "indeterminado",
                "mensaje": "La URL no corresponde al bucket de evidencia."}

    try:
        contenido = sb_manager.client.storage.from_(bucket_evidencia()).download(ruta)
    except Exception as exc:  # noqa: BLE001
        return {"estado": "desaparecida", "ruta": ruta,
                "mensaje": f"El archivo ya no está en Storage: {exc}"}

    actual = hashlib.sha256(contenido).hexdigest()
    if actual == esperado:
        return {"estado": "intacta", "ruta": ruta, "sha256": actual}
    return {"estado": "alterada", "ruta": ruta,
            "sha256_esperado": esperado, "sha256_actual": actual,
            "mensaje": "El contenido cambió desde que se subió."}


def _ruta_de_evidencia(referencia: Any) -> Optional[str]:
    """
    Ruta del objeto dentro del bucket de evidencia, venga como venga.

    En `bug_tickets.evidencia[]` conviven tres formas, y las tres tienen que
    resolver porque los tickets ya guardados no se reescriben (esa es la regla
    central del módulo):

    * la ruta pelada (`2026/AGOSTO/BUG-0001/clip-1234.mp4`) — lo que desde este
      cambio se guarda en el campo `path`;
    * la URL con forma pública (`.../object/public/ticket-evidencia/<ruta>`) —
      lo que se guardó en `url` hasta ahora, y que el navegador no puede abrir
      porque el bucket es privado;
    * una URL firmada (`.../object/sign/ticket-evidencia/<ruta>?token=...`), por
      si alguna quedó copiada en la base.

    Cualquier otra cosa —una URL del bucket `archivos`, por ejemplo— devuelve
    `None`: firmar a ciegas la ruta de otro bucket daría acceso a archivos que
    no son evidencia de este ticket.
    """
    texto = str(referencia or "").strip()
    if not texto:
        return None

    # Ruta pelada: ni esquema ni la marca de un endpoint de Storage.
    if "://" not in texto and "/object/" not in texto:
        return texto.lstrip("/") or None

    nombre = bucket_evidencia()
    for marca in (f"/object/public/{nombre}/", f"/object/sign/{nombre}/", f"/object/{nombre}/"):
        if marca in texto:
            ruta = unquote(texto.split(marca, 1)[1].split("?", 1)[0])
            return ruta or None
    return None


def url_firmada_evidencia(referencia: Any, expira_en: int = SEGUNDOS_URL_FIRMADA) -> Dict[str, Any]:
    """
    URL temporal con la que el navegador sí puede abrir un adjunto.

    Es la lectura que faltaba: el bucket de evidencia es privado, así que la
    URL guardada en el ticket no abre nada (ver `SEGUNDOS_URL_FIRMADA`). Aquí
    se pide una firma nueva cada vez, con caducidad, en vez de guardar un
    enlace permanente.

    Devuelve `{success, url, ruta, expira_en}` o `{success: False, message}`
    con la causa en un mensaje que diga qué hacer — que es lo que no tenía el
    `NoSuchBucket` crudo que veía el usuario.
    """
    from api.services.supabase_manager import sb_manager

    if not sb_manager.is_configured:
        return {"success": False,
                "message": "Supabase no está configurado: no hay de dónde leer la evidencia."}

    ruta = _ruta_de_evidencia(referencia)
    if not ruta:
        return {"success": False,
                "message": "La referencia guardada no corresponde al bucket de evidencia."}

    try:
        firma = sb_manager.client.storage.from_(bucket_evidencia()).create_signed_url(ruta, expira_en)
    except Exception as exc:  # noqa: BLE001
        # Aquí es donde asoma el bucket que de verdad falta: si
        # `ticket-evidencia` no está creado en el proyecto, Storage responde
        # `Bucket not found` y el mensaje lo dice con el nombre y el remedio.
        return {"success": False,
                "message": f"No se pudo abrir la evidencia del bucket "
                           f"{bucket_evidencia()!r}: {exc}"}

    if isinstance(firma, dict):
        url = str(firma.get("signedURL") or firma.get("signedUrl") or firma.get("signed_url") or "")
    else:
        url = str(firma or "")
    if not url:
        return {"success": False, "message": "Storage no devolvió URL firmada para la evidencia."}

    return {"success": True, "url": url, "ruta": ruta, "expira_en": expira_en}


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

    if len(contenido) > MAX_BYTES_SUBIDA_JSON:
        # No es un capricho del servidor: por esta ruta el archivo va dentro
        # del JSON de la petición y la plataforma corta el cuerpo en 4.5 MB.
        # Los archivos grandes tienen su propio camino (`url_de_subida_firmada`)
        # y el mensaje lo dice, porque el usuario no tiene por qué deducirlo.
        return {"success": False,
                "message": f"El archivo pesa {len(contenido)} bytes y por esta vía "
                           f"solo caben {MAX_BYTES_SUBIDA_JSON}. Los archivos grandes "
                           f"se suben directo a Storage con una URL firmada "
                           f"(hasta {MAX_BYTES_SUBIDA_DIRECTA} bytes)."}

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


def url_de_subida_firmada(nombre: Any, cliente: Any = None,
                          fecha: Any = None) -> Dict[str, Any]:
    """
    URL firmada para que el navegador suba el archivo **directo** a Storage.

    Es la ruta de los archivos grandes. `subir()` recibe el archivo en base64
    dentro del JSON de la petición, y ese JSON es el cuerpo de una función
    serverless que la plataforma corta en 4.5 MB: por ahí no pasa un adjunto
    de 20 MB, ni pasará, porque el límite no es del código. Con la URL firmada
    los bytes van del navegador a Storage sin tocar la función, y el tope
    vuelve a ser el del bucket.

    Devuelve `{success, uploadUrl, fileUrl, path}`:

    * `uploadUrl` — el destino del `PUT` (lleva el token dentro);
    * `fileUrl`   — la URL pública que se guarda en la celda cuando el `PUT`
      termina, la misma que devolvería `subir()`;
    * `path`      — la clave del objeto, por si el llamador quiere archivarlo
      después (`archivar_cotizacion`).

    La ruta la decide el servidor, nunca el cliente: firmar la clave que mande
    el navegador dejaría escribir en cualquier parte del bucket.
    """
    from api.services.supabase_manager import sb_manager

    if not sb_manager.is_configured:
        return {"success": False,
                "message": "Supabase no está configurado: no se puede subir el archivo."}

    ruta = ruta_de_archivo(nombre, cliente, fecha)

    try:
        almacen = sb_manager.client.storage.from_(bucket())
        firma = almacen.create_signed_upload_url(ruta)
        url_publica = almacen.get_public_url(ruta)
    except Exception as exc:  # noqa: BLE001
        return {"success": False,
                "message": f"No se pudo preparar la subida directa: {exc}"}

    subida = ""
    if isinstance(firma, dict):
        subida = str(firma.get("signed_url") or firma.get("signedUrl") or "")
    if not subida:
        return {"success": False,
                "message": "Storage no devolvió la URL firmada de subida."}

    return {"success": True, "uploadUrl": subida, "fileUrl": url_publica,
            "path": ruta, "maxBytes": MAX_BYTES_SUBIDA_DIRECTA}


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


def _ruta_desde_url(file_url: Any, nombre_bucket: Optional[str] = None) -> Optional[str]:
    """
    Clave del objeto a partir de su URL pública.

    Formato de Supabase: `.../storage/v1/object/public/<bucket>/<ruta>`.

    `nombre_bucket` por defecto es el bucket general (`bucket()`), que es lo
    que necesitan `archivar_cotizacion` y los adjuntos del tracker. La
    evidencia de tickets vive en otro bucket y lo pasa explícito.
    """
    texto = str(file_url or "")
    marca = f"/object/public/{nombre_bucket or bucket()}/"
    if marca not in texto:
        return None
    ruta = texto.split(marca, 1)[1].split("?")[0]
    return ruta or None
