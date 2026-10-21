"""
El dashboard de la Pre Work Order: el aviso para regenerarlo.

Cuando alguien sube a la Pre Work Order un documento con datos (xlsx, xls, csv,
pdf o docx), este módulo le avisa al repositorio `Agente_Full` con un
`repository_dispatch` de GitHub. Allá, un Action corre el pipeline de tres
agentes (`agente_full/pipeline_dashboard.py`, adaptación de `gs3.py`), valida
la app y la publica en Streamlit Cloud. La liga corta (`DASHBOARD_PWO_URL`) no
cambia: siempre enseña el último dashboard que pasó las pruebas.

Por qué un aviso y no generar aquí: el pipeline tarda minutos, necesita
Chromium y ejecuta código escrito por un modelo. Nada de eso cabe en una
función serverless de Vercel, y lo último no debe correr junto a las claves de
la base de datos.

Qué se valida antes de avisar, y por qué:

* **Solo documentos con datos.** Las fotos, videos y layouts de la obra se
  suben por los mismos botones; con ellos el dashboard se reemplazaría por el
  análisis de una foto de fachada.
* **Solo URLs del Storage de Holtmont.** La API no tiene sesión (deuda
  documentada en `api/main.py`), así que el endpoint se puede llamar a mano;
  esto impide que alguien mande al Action a descargar cualquier cosa.
* **El token nunca sale en un mensaje.** Si GitHub lo repitiera en su
  respuesta, se tacha antes de devolverla al navegador.

El apartado **Dashboard Streamlit** (bandera `dashboard_streamlit`, hoy solo
ANTONIO_SALAZAR) usa el mismo aviso, pero además necesita saber cuándo terminó
para enseñar "¡Procesamiento Exitoso!". Por eso `procesar` le pone a cada aviso
una `solicitud` que el Action lleva en su `run-name`, y `estado` busca esa
corrida en GitHub y dice en qué va.

Configuración (variables de entorno del despliegue):

    DASHBOARD_PWO_TOKEN  obligatoria. Token con Contents: Read and write (el
                         aviso) y Actions: Read (el seguimiento del apartado)
    DASHBOARD_PWO_REPO   opcional; por defecto Luis-py-stack/Agente_Full
    DASHBOARD_PWO_URL    opcional; por defecto la liga corta de Streamlit Cloud

Repositorio y liga no son secretos y traen valor por defecto. Antes, un
despliegue sin variables pedía las tres; ahora solo pide el token, que es lo
único que no puede vivir en el código.
"""

from __future__ import annotations

import json
import os
import posixpath
import re
import urllib.error
import urllib.parse
import urllib.request
import uuid
from typing import Any, Callable, Dict, Mapping, Optional, Tuple

EVENTO = "pwo_dashboard"
EXTENSIONES_DE_DATOS = (".xlsx", ".xls", ".csv", ".pdf", ".docx")
RUTA_PUBLICA_STORAGE = "/storage/v1/object/public/"
_REPO_VALIDO = re.compile(r"^[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+$")
# Los de agente_full/README.md. El token no tiene valor por defecto: es secreto.
_POR_DEFECTO = {
    "DASHBOARD_PWO_REPO": "Luis-py-stack/Agente_Full",
    "DASHBOARD_PWO_URL": "https://agentefull-mhytzkjfr38ukzqxnuxbkf.streamlit.app/",
}
# El `run-name` de agente_full/workflow_dashboard_pwo.yml. Si cambia allá, el
# seguimiento deja de encontrar la corrida (lo cuida tests/test_dashboard_pwo.py).
TITULO_DE_CORRIDA = "Dashboard PWO {solicitud}"
_SOLICITUD_VALIDA = re.compile(r"[0-9a-f]{12}")
_EN_MARCHA = {"in_progress": ("PROCESANDO", "Generando y validando el dashboard; tarda unos minutos.")}
_EN_COLA = ("EN_COLA", "En cola en GitHub.")
_MOTIVOS_DE_FALLO = {
    "failure": ("El dashboard no pasó las pruebas o el Action falló; la liga sigue mostrando el "
                "dashboard anterior."),
    "cancelled": "Se canceló en GitHub: llegó un archivo más reciente o alguien la detuvo.",
    "timed_out": "El procesamiento rebasó el tiempo máximo del Action y se detuvo.",
}

Enviar = Callable[[str, Dict[str, Any], Dict[str, str]], Tuple[int, str]]
Consultar = Callable[[str, Dict[str, str]], Tuple[int, str]]


def _ruta_de(url_o_nombre: Any) -> str:
    texto = str(url_o_nombre or "")
    return urllib.parse.unquote(urllib.parse.urlsplit(texto).path or texto)


def es_archivo_de_datos(url_o_nombre: Any) -> bool:
    """Si el archivo es de los que regeneran el dashboard (no fotos ni videos)."""
    return _ruta_de(url_o_nombre).lower().endswith(EXTENSIONES_DE_DATOS)


def _configuracion(entorno: Mapping[str, str]) -> Dict[str, str]:
    return {clave: str(entorno.get(clave) or "").strip() or _POR_DEFECTO.get(clave, "")
            for clave in ("DASHBOARD_PWO_REPO", "DASHBOARD_PWO_TOKEN", "DASHBOARD_PWO_URL")}


def link(entorno: Optional[Mapping[str, str]] = None) -> Dict[str, Any]:
    """La liga corta y si la PWO puede pedir que se regenere."""
    config = _configuracion(os.environ if entorno is None else entorno)
    return {"success": True, "url": config["DASHBOARD_PWO_URL"], "configurado": all(config.values())}


def _esta_en_el_storage(url: str, supabase_url: str) -> bool:
    if not supabase_url or not url:
        return False
    permitido = urllib.parse.urlsplit(supabase_url.rstrip("/"))
    pedido = urllib.parse.urlsplit(url)
    ruta = posixpath.normpath(urllib.parse.unquote(pedido.path))
    return ((pedido.scheme, pedido.netloc) == (permitido.scheme, permitido.netloc)
            and ruta.startswith(RUTA_PUBLICA_STORAGE))


def _repo_valido(repo: str) -> bool:
    return bool(_REPO_VALIDO.match(repo)) and not any(p in (".", "..") for p in repo.split("/"))


def _motivo_de_configuracion(config: Dict[str, str]) -> Optional[str]:
    """Qué le falta a la configuración del despliegue, o None si está completa."""
    if not config["DASHBOARD_PWO_TOKEN"]:
        return ("Falta configurar DASHBOARD_PWO_TOKEN en el despliegue: agrégalo en Vercel "
                "(Settings → Environment Variables, entorno Production) y vuelve a desplegar.")
    if not _repo_valido(config["DASHBOARD_PWO_REPO"]):
        return (f"DASHBOARD_PWO_REPO debe tener la forma dueño/repositorio "
                f"(llegó '{config['DASHBOARD_PWO_REPO']}').")
    return None


def _motivo_de_rechazo(file_url: str, config: Dict[str, str], entorno: Mapping[str, str]) -> Optional[str]:
    """Por qué no se puede avisar, o None si todo está en orden."""
    motivo = _motivo_de_configuracion(config)
    if motivo:
        return motivo
    if not _esta_en_el_storage(file_url, str(entorno.get("SUPABASE_URL") or "").strip()):
        return "El archivo no está en el Storage de Holtmont; no se manda a generar."
    if not es_archivo_de_datos(file_url):
        return (f"{posixpath.basename(_ruta_de(file_url))} no es un documento con datos "
                f"(xlsx, xls, csv, pdf o docx).")
    return None


def _abrir(peticion: urllib.request.Request, timeout: float) -> Tuple[int, str]:
    """(estado, texto) de la petición, también cuando el estado es de error."""
    try:
        with urllib.request.urlopen(peticion, timeout=timeout) as respuesta:
            return respuesta.status, respuesta.read().decode("utf-8", errors="replace")
    except urllib.error.HTTPError as exc:
        return exc.code, exc.read().decode("utf-8", errors="replace")


def _post_json(url: str, cuerpo: Dict[str, Any], encabezados: Dict[str, str],
               timeout: float = 15.0) -> Tuple[int, str]:
    """POST con JSON; devuelve (estado, texto) también cuando el estado es de error."""
    peticion = urllib.request.Request(
        url, data=json.dumps(cuerpo).encode("utf-8"), method="POST",
        headers={**encabezados, "Content-Type": "application/json", "User-Agent": "holtmont-pwo-dashboard"})
    return _abrir(peticion, timeout)


def _get_json(url: str, encabezados: Dict[str, str], timeout: float = 15.0) -> Tuple[int, str]:
    """GET; devuelve (estado, texto) también cuando el estado es de error."""
    peticion = urllib.request.Request(
        url, method="GET", headers={**encabezados, "User-Agent": "holtmont-pwo-dashboard"})
    return _abrir(peticion, timeout)


def _encabezados_de_github(token: str) -> Dict[str, str]:
    return {"Authorization": f"Bearer {token}", "Accept": "application/vnd.github+json",
            "X-GitHub-Api-Version": "2022-11-28"}


def _carga_del_aviso(file_url: str, folio: str, usuario: str, solicitud: str) -> Dict[str, str]:
    """El `client_payload`; `solicitud` solo viaja si la hay (la PWO no la usa)."""
    carga = {"file_url": file_url, "folio": folio, "usuario": usuario}
    return {**carga, "solicitud": solicitud} if solicitud else carga


def _avisar_a_github(file_url: str, folio: str, usuario: str, config: Dict[str, str],
                     enviar: Enviar, solicitud: str = "") -> Tuple[bool, str]:
    """El `repository_dispatch`; (éxito, mensaje para la pantalla) sin el token."""
    token = config["DASHBOARD_PWO_TOKEN"]
    cuerpo = {"event_type": EVENTO, "client_payload": _carga_del_aviso(file_url, folio, usuario, solicitud)}
    encabezados = _encabezados_de_github(token)
    nombre = posixpath.basename(_ruta_de(file_url))
    try:
        estado, texto = enviar(f"https://api.github.com/repos/{config['DASHBOARD_PWO_REPO']}/dispatches",
                               cuerpo, encabezados)
    except OSError as exc:
        return False, f"No se pudo avisar a GitHub: {exc}".replace(token, "***")
    print(f"[dashboard_pwo] {usuario or 'sin usuario'} pidió el dashboard de {nombre} "
          f"(folio {folio or 'sin folio'}): GitHub {estado}")
    if estado != 204:
        return False, f"GitHub respondió {estado}: {texto[:200]}".replace(token, "***")
    return True, f"El dashboard se está actualizando con {nombre}; tarda unos minutos."


def disparar(file_url: str, folio: str = "", usuario: str = "",
             entorno: Optional[Mapping[str, str]] = None, enviar: Optional[Enviar] = None,
             solicitud: str = "") -> Dict[str, Any]:
    """Pide al Action de Agente_Full que regenere el dashboard con `file_url`.

    `solicitud` (opcional) viaja en el aviso y el Action la pone en el nombre
    de la corrida; es lo que permite a `estado` encontrarla después.
    """
    entorno = os.environ if entorno is None else entorno
    file_url = str(file_url or "").strip()
    config = _configuracion(entorno)
    respuesta: Dict[str, Any] = {"success": False, "url": config["DASHBOARD_PWO_URL"]}
    motivo = _motivo_de_rechazo(file_url, config, entorno)
    if motivo:
        return {**respuesta, "message": motivo}
    exito, mensaje = _avisar_a_github(file_url, folio or "", usuario or "", config, enviar or _post_json,
                                      solicitud)
    return {**respuesta, "success": exito, "message": mensaje}


# --- Apartado Dashboard Streamlit: procesar y seguir la corrida -------------

def procesar(file_url: str, usuario: str = "", entorno: Optional[Mapping[str, str]] = None,
             enviar: Optional[Enviar] = None) -> Dict[str, Any]:
    """El botón Procesar: avisa al Action y devuelve la `solicitud` para seguirlo.

    La solicitud la inventa el servidor, no el navegador: así siempre tiene la
    forma que `estado` acepta y no se puede reutilizar la de otra persona por
    accidente.
    """
    solicitud = uuid.uuid4().hex[:12]
    respuesta = disparar(file_url, "", usuario, entorno=entorno, enviar=enviar, solicitud=solicitud)
    return {**respuesta, "solicitud": solicitud} if respuesta["success"] else respuesta


def _url_del_repo(config: Dict[str, str]) -> str:
    repo = config["DASHBOARD_PWO_REPO"]
    return f"https://github.com/{repo}" if _repo_valido(repo) else ""


def _motivo_para_no_consultar(solicitud: str, config: Dict[str, str]) -> Optional[str]:
    """Por qué no se puede preguntar por la corrida, o None si todo está en orden."""
    motivo = _motivo_de_configuracion(config)
    if motivo:
        return motivo
    if not _SOLICITUD_VALIDA.fullmatch(solicitud):
        return "La solicitud no es válida; vuelve a procesar el archivo."
    return None


def _corrida_de(texto: str, solicitud: str) -> Optional[Dict[str, Any]]:
    """La corrida del Action cuyo nombre lleva esta solicitud, si ya existe."""
    try:
        corridas = json.loads(texto).get("workflow_runs") or []
    except (ValueError, AttributeError):
        return None
    titulo = TITULO_DE_CORRIDA.format(solicitud=solicitud)
    return next((c for c in corridas if isinstance(c, dict) and c.get("display_title") == titulo), None)


def _estado_de_corrida(corrida: Optional[Dict[str, Any]]) -> Dict[str, str]:
    """La corrida de GitHub traducida a lo que enseña la pantalla."""
    if corrida is None:
        return {"estado": "SIN_INICIAR", "message": "Esperando a que GitHub arranque el procesamiento.",
                "run_url": ""}
    run_url = str(corrida.get("html_url") or "")
    if corrida.get("status") != "completed":
        estado, mensaje = _EN_MARCHA.get(str(corrida.get("status")), _EN_COLA)
        return {"estado": estado, "message": mensaje, "run_url": run_url}
    conclusion = str(corrida.get("conclusion") or "")
    if conclusion == "success":
        return {"estado": "EXITOSO", "message": "Dashboard generado en GitHub.", "run_url": run_url}
    mensaje = _MOTIVOS_DE_FALLO.get(conclusion, f"El Action de GitHub terminó con '{conclusion}'.")
    return {"estado": "ERROR", "message": mensaje, "run_url": run_url}


def _rechazo_de_github(codigo: int, texto: str, config: Dict[str, str]) -> str:
    mensaje = f"GitHub respondió {codigo}: {texto[:200]}"
    if codigo in (403, 404):
        mensaje += f" (el token necesita permiso Actions: Read en {config['DASHBOARD_PWO_REPO']})"
    return mensaje


def estado(solicitud: str, entorno: Optional[Mapping[str, str]] = None,
           consultar: Optional[Consultar] = None) -> Dict[str, Any]:
    """En qué va la corrida del Action que pidió `procesar`.

    `estado` es SIN_INICIAR (GitHub todavía no la crea), EN_COLA, PROCESANDO,
    EXITOSO o ERROR. `success: false` solo cuando no se pudo preguntar
    (configuración o red), para que la pantalla reintente en vez de rendirse.
    """
    entorno = os.environ if entorno is None else entorno
    solicitud = str(solicitud or "").strip()
    config = _configuracion(entorno)
    respuesta: Dict[str, Any] = {"success": False, "url": config["DASHBOARD_PWO_URL"],
                                 "repo_url": _url_del_repo(config)}
    motivo = _motivo_para_no_consultar(solicitud, config)
    if motivo:
        return {**respuesta, "message": motivo}
    token = config["DASHBOARD_PWO_TOKEN"]
    url = (f"https://api.github.com/repos/{config['DASHBOARD_PWO_REPO']}/actions/runs"
           "?event=repository_dispatch&per_page=50")
    try:
        codigo, texto = (consultar or _get_json)(url, _encabezados_de_github(token))
    except OSError as exc:
        return {**respuesta, "message": f"No se pudo consultar a GitHub: {exc}".replace(token, "***")}
    if codigo != 200:
        return {**respuesta, "message": _rechazo_de_github(codigo, texto, config).replace(token, "***")}
    return {**respuesta, "success": True, **_estado_de_corrida(_corrida_de(texto, solicitud))}
