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

Configuración (variables de entorno del despliegue):

    DASHBOARD_PWO_REPO   dueño/repositorio, p. ej. Luis-py-stack/Agente_Full
    DASHBOARD_PWO_TOKEN  token fine-grained con Contents: Read and write
    DASHBOARD_PWO_URL    la liga corta de Streamlit Cloud
"""

from __future__ import annotations

import json
import os
import posixpath
import re
import urllib.error
import urllib.parse
import urllib.request
from typing import Any, Callable, Dict, Mapping, Optional, Tuple

EVENTO = "pwo_dashboard"
EXTENSIONES_DE_DATOS = (".xlsx", ".xls", ".csv", ".pdf", ".docx")
RUTA_PUBLICA_STORAGE = "/storage/v1/object/public/"
_REPO_VALIDO = re.compile(r"^[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+$")

Enviar = Callable[[str, Dict[str, Any], Dict[str, str]], Tuple[int, str]]


def _ruta_de(url_o_nombre: Any) -> str:
    texto = str(url_o_nombre or "")
    return urllib.parse.unquote(urllib.parse.urlsplit(texto).path or texto)


def es_archivo_de_datos(url_o_nombre: Any) -> bool:
    """Si el archivo es de los que regeneran el dashboard (no fotos ni videos)."""
    return _ruta_de(url_o_nombre).lower().endswith(EXTENSIONES_DE_DATOS)


def _configuracion(entorno: Mapping[str, str]) -> Dict[str, str]:
    return {clave: str(entorno.get(clave) or "").strip()
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


def _motivo_de_rechazo(file_url: str, config: Dict[str, str], entorno: Mapping[str, str]) -> Optional[str]:
    """Por qué no se puede avisar, o None si todo está en orden."""
    faltan = [clave for clave, valor in config.items() if not valor]
    if faltan:
        return "Falta configurar " + ", ".join(faltan) + " en el despliegue."
    if not _repo_valido(config["DASHBOARD_PWO_REPO"]):
        return (f"DASHBOARD_PWO_REPO debe tener la forma dueño/repositorio "
                f"(llegó '{config['DASHBOARD_PWO_REPO']}').")
    if not _esta_en_el_storage(file_url, str(entorno.get("SUPABASE_URL") or "").strip()):
        return "El archivo no está en el Storage de Holtmont; no se manda a generar."
    if not es_archivo_de_datos(file_url):
        return (f"{posixpath.basename(_ruta_de(file_url))} no es un documento con datos "
                f"(xlsx, xls, csv, pdf o docx).")
    return None


def _post_json(url: str, cuerpo: Dict[str, Any], encabezados: Dict[str, str],
               timeout: float = 15.0) -> Tuple[int, str]:
    """POST con JSON; devuelve (estado, texto) también cuando el estado es de error."""
    peticion = urllib.request.Request(
        url, data=json.dumps(cuerpo).encode("utf-8"), method="POST",
        headers={**encabezados, "Content-Type": "application/json", "User-Agent": "holtmont-pwo-dashboard"})
    try:
        with urllib.request.urlopen(peticion, timeout=timeout) as respuesta:
            return respuesta.status, respuesta.read().decode("utf-8", errors="replace")
    except urllib.error.HTTPError as exc:
        return exc.code, exc.read().decode("utf-8", errors="replace")


def _avisar_a_github(file_url: str, folio: str, usuario: str, config: Dict[str, str],
                     enviar: Enviar) -> Tuple[bool, str]:
    """El `repository_dispatch`; (éxito, mensaje para la pantalla) sin el token."""
    token = config["DASHBOARD_PWO_TOKEN"]
    cuerpo = {"event_type": EVENTO, "client_payload": {"file_url": file_url, "folio": folio, "usuario": usuario}}
    encabezados = {"Authorization": f"Bearer {token}", "Accept": "application/vnd.github+json",
                   "X-GitHub-Api-Version": "2022-11-28"}
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
             entorno: Optional[Mapping[str, str]] = None, enviar: Optional[Enviar] = None) -> Dict[str, Any]:
    """Pide al Action de Agente_Full que regenere el dashboard con `file_url`."""
    entorno = os.environ if entorno is None else entorno
    file_url = str(file_url or "").strip()
    config = _configuracion(entorno)
    respuesta: Dict[str, Any] = {"success": False, "url": config["DASHBOARD_PWO_URL"]}
    motivo = _motivo_de_rechazo(file_url, config, entorno)
    if motivo:
        return {**respuesta, "message": motivo}
    exito, mensaje = _avisar_a_github(file_url, folio or "", usuario or "", config, enviar or _post_json)
    return {**respuesta, "success": exito, "message": mensaje}
