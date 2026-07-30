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
la ruta del objeto: `2026/03 - MARZO/ACME INDUSTRIAL/cotizacion.pdf`. El resultado
para el usuario es el mismo —los objetos se listan por prefijo— y no hay que
crear nada antes de subir.
"""

from __future__ import annotations

import base64
import os
import re
import unicodedata
import urllib.parse
from datetime import datetime
from typing import Any, Dict, Optional, Tuple

BUCKET_ENV = "SUPABASE_BUCKET"
BUCKET_POR_DEFECTO = "archivos"

# Igual que el original: sin tipo declarado, octet-stream. Pasa con .dwg y .zip,
# que el navegador no sabe etiquetar.
MIME_POR_DEFECTO = "application/octet-stream"

# Nombres de carpeta de mes **tal cual los escribe el original** en
# `processQuoteRow` (CODIGO.js): con el número delante y separado por " - ".
# El prefijo numérico no es decorativo: es lo que hace que el listado del banco
# salga en orden cronológico y no alfabético (con solo el nombre, ABRIL queda
# antes de ENERO). Aquí faltaba, así que el árbol del banco de cotizaciones no
# coincidía con el de Drive y quien mirara el bucket vería otra estructura.
MESES = ["01 - ENERO", "02 - FEBRERO", "03 - MARZO", "04 - ABRIL",
         "05 - MAYO", "06 - JUNIO", "07 - JULIO", "08 - AGOSTO",
         "09 - SEPTIEMBRE", "10 - OCTUBRE", "11 - NOVIEMBRE", "12 - DICIEMBRE"]


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


def _momento(fecha: Any) -> datetime:
    if isinstance(fecha, datetime):
        return fecha
    from api.services.tracker_rules import parse_sheet_date

    return parse_sheet_date(fecha) or datetime.now()


def carpeta_de_archivo(cliente: Any = None, fecha: Any = None) -> str:
    """
    Prefijo de la carpeta: `AÑO/MES` o `AÑO/MES/CLIENTE`.

    Es el equivalente de la cadena `getBankRootFolder → getOrCreateFolder(año) →
    getOrCreateFolder(mes) → getOrCreateFolder(cliente)` del original. Se separó
    de `ruta_de_archivo` porque archivar necesita **solo** el destino de la
    carpeta: el nombre del archivo tiene que conservarse tal cual.
    """
    momento = _momento(fecha)
    partes = [str(momento.year), MESES[momento.month - 1]]
    if cliente:
        partes.append(limpiar_segmento(cliente, "SIN_CLIENTE"))
    return "/".join(partes)


def ruta_de_archivo(nombre: Any, cliente: Any = None, fecha: Any = None) -> str:
    """
    Ruta del objeto. Con cliente, la del banco: `AÑO/MES/CLIENTE/archivo`.

    Sin cliente cae en `AÑO/MES/archivo`, que es el equivalente de subir a la
    carpeta raíz de uploads del original.
    """
    momento = _momento(fecha)
    partes = [carpeta_de_archivo(cliente, momento)]

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

    Equivalente de `archiveFile` del original. En Drive era mover el archivo
    entre carpetas; aquí es un `move` de la clave del objeto, que es la misma
    operación sobre el mismo dato.

    Si la URL no es de este bucket se devuelve `success: False` sin tocar nada,
    igual que el original ignoraba lo que no fuera una URL de Drive.

    **El nombre del archivo se conserva.** Antes el destino se calculaba con
    `ruta_de_archivo`, que le pega una marca de tiempo nueva: archivar dos veces
    el mismo archivo lo renombraba (`plano-1.dwg` → `plano-1-2.dwg` →
    `plano-1-2-3.dwg`) y la comparación con `ruta_actual` nunca podía dar igual,
    así que el "ya estaba archivado" era inalcanzable. `archiveFile` compara la
    carpeta padre y devuelve "Already there" sin tocar el archivo; eso es lo que
    hace falta para que el lote de `archivar_lote_cotizaciones` se pueda correr
    todos los días sin mover nada la segunda vez.
    """
    from api.services.supabase_manager import sb_manager

    if not sb_manager.is_configured:
        return {"success": False, "message": "Supabase no está configurado."}

    ruta_actual = _ruta_desde_url(file_url)
    if not ruta_actual:
        return {"success": False, "message": "La URL no corresponde a este bucket."}

    nombre = os.path.basename(ruta_actual)
    destino = f"{carpeta_de_archivo(cliente, fecha)}/{nombre}"
    if ruta_actual == destino:
        return {"success": True, "message": "Ya estaba archivado.", "path": destino,
                "movido": False}

    try:
        almacen = sb_manager.client.storage.from_(bucket())
        almacen.move(ruta_actual, destino)
        url = almacen.get_public_url(destino)
    except Exception as exc:  # noqa: BLE001
        return {"success": False, "message": f"No se pudo archivar: {exc}"}

    return {"success": True, "fileUrl": url, "path": destino, "message": "Archivado.",
            "movido": True}


# Columnas de las que `processQuoteRow` saca cliente, fecha y archivos, en el
# mismo orden de preferencia del original.
_COL_FECHA = ["FECHA", "FECHA INICIO", "F. INICIO", "F. VISITA", "F. ENTREGA",
              "ALTA", "FECHA_ALTA"]
_COL_ARCHIVO = ["COTIZACION", "ARCHIVO", "LINK", "EVIDENCIA"]


def separar_urls(valor: Any) -> list:
    """
    Las URLs de una celda que puede traer varias.

    El original parte con `split(/[\\n\\s,]+/)`, es decir, también por espacios
    sueltos. Aquí eso **no** sirve: nuestras rutas de Storage llevan espacios
    dentro (`2026/03 - MARZO/ACME INDUSTRIAL/plano.pdf`), así que partir por
    espacio troceaba una sola URL en tres pedazos y solo el primero pasaba el
    filtro de "empieza con HTTP" — se archivaba una ruta truncada. En Drive el
    problema no existe porque sus URLs son `.../file/d/<id>`, sin espacios.

    Se parte por los separadores que de verdad usa el campo (salto de línea,
    coma, tabulador, punto y coma) y, dentro de cada trozo, solo por el espacio
    que **precede a otra URL**. Un espacio dentro de una URL nunca va seguido de
    `http`, así que la distinción es exacta.
    """
    urls = []
    for trozo in re.split(r"[\n\r\t,;]+", str(valor or "")):
        for pieza in re.split(r"\s+(?=https?://)", trozo.strip(), flags=re.IGNORECASE):
            pieza = pieza.strip()
            if pieza.upper().startswith("HTTP"):
                urls.append(pieza)
    return urls


def archivar_fila_cotizacion(row: Dict[str, Any]) -> Dict[str, Any]:
    """
    Port de `processQuoteRow`: archiva todos los archivos de una cotización.

    Igual que el original: si falta cliente, fecha o archivo la fila se salta con
    `"Missing Data"` (el lote no lo cuenta como error), la fecha se parsea con
    tolerancia, y el campo de archivo puede traer **varias URLs** separadas por
    salto de línea, espacio o coma — se archiva cada una.
    """
    from api.services import tracker_rules as rules

    cliente = rules.pick_task_value(row, ["CLIENTE"])
    fecha_bruta = rules.pick_task_value(row, _COL_FECHA)
    archivos = rules.pick_task_value(row, _COL_ARCHIVO)

    if not (str(cliente or "").strip() and str(fecha_bruta or "").strip()
            and str(archivos or "").strip()):
        return {"success": False, "message": "Missing Data", "processed": 0}

    fecha = fecha_bruta if isinstance(fecha_bruta, datetime) else rules.parse_sheet_date(fecha_bruta)
    if not fecha:
        return {"success": False, "message": "Invalid Date", "processed": 0}

    urls = separar_urls(archivos)
    if not urls:
        return {"success": False, "message": "Missing Data", "processed": 0}

    procesados = 0
    fallos = []
    for url in urls:
        res = archivar_cotizacion(url, cliente, fecha)
        if res.get("success"):
            procesados += 1
        else:
            fallos.append(res.get("message", "error"))

    return {"success": True, "processed": procesados, "errors": fallos}


def archivar_lote_cotizaciones() -> Dict[str, Any]:
    """
    Port de `batchArchiveExistingQuotes` (+ `runFullArchivingBatch`).

    Recorre la tabla maestra de ventas y reubica los archivos de cada cotización
    bajo `AÑO/MES/CLIENTE`. En el original lo disparaba el menú del Spreadsheet;
    aquí es un endpoint, y por eso devuelve el resumen en vez de abrir un
    `ui.alert`.

    No existía equivalente: el archivado estaba solo para un archivo suelto, así
    que las 4.600 cotizaciones ya cargadas nunca se organizaban.
    """
    from api.services import tracker_rules as rules
    from api.services.tracker_store import read_rows

    activas, historico, _ = read_rows(rules.SALES_MASTER_SHEET)

    procesados = 0
    errores = []
    for row in list(activas) + list(historico):
        res = archivar_fila_cotizacion(row)
        if res.get("success"):
            procesados += res.get("processed", 0)
            errores.extend(res.get("errors") or [])
        elif res.get("message") != "Missing Data":
            # "Missing Data" no es un error: es una fila sin cliente, sin fecha o
            # sin archivo, que el original también salta en silencio.
            errores.append(res.get("message", "error"))

    mensaje = f"Batch Archive: {procesados} archivos procesados. Errores: {len(errores)}"
    registrar_auditoria("BATCH_ARCHIVE", mensaje)
    return {"success": True, "message": mensaje,
            "processed": procesados, "errors": errores[:20]}


def registrar_auditoria(accion: str, detalle: str) -> None:
    """
    `registrarLog("SYSTEM", accion, detalle)` del original.

    `backend.services.auditoria` ya se traga sus propios fallos, pero el import
    también puede fallar (la capa relacional es opcional), así que va envuelto:
    un lote que archivó bien no debe reportarse como error por no poder anotarlo.
    """
    try:
        from backend.services import auditoria

        auditoria.registrar("SYSTEM", accion, detalle)
    except Exception as exc:  # noqa: BLE001
        print(f"[storage] {accion}: {detalle} (sin auditoría: {exc})")


def _ruta_desde_url(file_url: Any) -> Optional[str]:
    """
    Clave del objeto a partir de su URL pública.

    Formato de Supabase: `.../storage/v1/object/public/<bucket>/<ruta>`.

    Se desescapa el porcentaje: las claves llevan espacios (`03 - MARZO`,
    `ACME INDUSTRIAL`) y en la URL pueden venir como `%20`, mientras que la API
    de Storage espera la clave literal. Sin esto, `move` sobre una URL escapada
    apuntaría a un objeto que no existe. Es inocuo cuando la URL no venía
    escapada: `limpiar_segmento` no deja `%` en los nombres.
    """
    texto = str(file_url or "")
    marca = f"/object/public/{bucket()}/"
    if marca not in texto:
        return None
    ruta = texto.split(marca, 1)[1].split("?")[0]
    return urllib.parse.unquote(ruta) or None
