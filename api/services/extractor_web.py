"""
Lectura del sitio web de un establecimiento del DENUE, sin navegador.

Por qué no crawl4ai
-------------------
El notebook usa `crawl4ai` + Playwright. Los dos necesitan un binario de
Chromium que no existe en el runtime de Vercel, y el bundle tiene 250 MB para
todo. Aquí se lee con `urllib.request` + `html.parser`, los dos de la biblioteca
estándar: cero dependencias nuevas.

Lo que eso cubre y lo que no está medido, no supuesto (plan §2.3, contra sitios
reales del DENUE):

    [OK]    WWW.GRUPOLAFE.COM        777 ms      443 chars
    [OK]    NORSK.MX                 430 ms    2,484 chars
    [OK]    WWW.ADTEC.COM.MX         662 ms       16 chars   <- arma su HTML con JS
    [FALLA] WWW.2MARQUITECTOS.COM               404          <- sitio muerto

La mayoría se resuelve en menos de un segundo. Queda un residuo real —páginas
que dependen de JS y sitios caídos— y para eso está la tercera capa (Tavily),
no este módulo.

⚠️ SEGURIDAD: esto es SSRF de manual
------------------------------------
La URL viene del dato del INEGI y, en el peor caso, del usuario. Un servidor que
descarga una URL ajena puede ser usado para alcanzar lo que el atacante no
alcanza: `127.0.0.1`, la red privada del despliegue o el endpoint de metadatos
de la nube (`169.254.169.254`), que en varios proveedores entrega credenciales.

Las defensas de §9 del plan, todas implementadas aquí:

  1. Lista blanca de esquemas: solo `http` y `https`. `file://`, `gopher://` y
     `ftp://` quedan fuera — `file:///etc/passwd` es la versión trivial de esto.
  2. Se resuelve el DNS y se rechaza si **cualquiera** de las direcciones del
     host es privada, loopback, link-local, reservada o multicast. Cualquiera,
     no la primera: un host con dos registros A (uno público y uno interno)
     pasaría revisando solo el primero.
  3. Las redirecciones NO se siguen solas. El manejador automático se apaga y
     cada salto se revalida entero, porque un `301` a `http://169.254.169.254`
     es exactamente el rodeo que la comprobación inicial no ve.
  4. Timeout de 8 s y techo de lectura de 400 KB. Sin techo, un servidor que
     escupe bytes sin parar agota la memoria de la función.
  5. `User-Agent` identificable y `robots.txt` respetado, con el mismo camino
     guardado que el resto (el `RobotFileParser` de la biblioteca abre la URL
     por su cuenta, sin timeout y sin ninguna de estas comprobaciones).

**Riesgo residual que queda por escrito:** entre la resolución del DNS y la
conexión, `urllib` vuelve a resolver el nombre. Un dominio hostil puede devolver
una IP pública en la primera consulta y una privada en la segunda (*DNS
rebinding*). Cerrarlo exige conectarse a la IP ya validada y mandar el `Host` a
mano, lo que rompe la validación del certificado en HTTPS. No se cierra aquí; se
documenta, y la ventana es de milisegundos contra un atacante que además tenga
que controlar un dominio del DENUE.
"""

from __future__ import annotations

import ipaddress
import socket
import urllib.error
import urllib.parse
import urllib.request
import urllib.robotparser
from html.parser import HTMLParser
from typing import Any, Callable, Dict, List, Optional, Tuple

ESQUEMAS_PERMITIDOS = ("http", "https")
TIEMPO_ESPERA_S = 8
TECHO_LECTURA_BYTES = 400 * 1024
MAXIMO_REDIRECCIONES = 3

# Identificable a propósito: quien vea este agente en sus registros tiene que
# poder saber quién es y a quién reclamarle.
USER_AGENT = "HoltmontProspeccion/1.0 (+https://holtmont.com)"

# Longitud por debajo de la cual el texto no sirve para nada. `WWW.ADTEC.COM.MX`
# devolvió 16 caracteres (§2.3): el HTML llega, pero el contenido lo arma el
# navegador. Se trata como "sin texto" para que caiga a la siguiente capa.
MINIMO_UTIL_CHARS = 120

MOTIVO_ESQUEMA = "esquema_no_permitido"
MOTIVO_DESTINO_INTERNO = "destino_interno"
MOTIVO_SIN_HOST = "sin_host"
MOTIVO_DNS = "dns_no_resuelve"
MOTIVO_ROBOTS = "robots_prohibe"
MOTIVO_HTTP = "error_http"
MOTIVO_RED = "error_de_red"
MOTIVO_REDIRECCIONES = "demasiadas_redirecciones"
MOTIVO_TEXTO_INSUFICIENTE = "texto_insuficiente"


def normalizar_url(www: Any) -> str:
    """
    `"WWW.GRUPOLAFE.COM"` -> `"https://WWW.GRUPOLAFE.COM"`.

    Solo **10** de las 2,848 URLs del DENUE traen esquema (§2.4). Sin
    anteponerlo, `urlparse` lee el dominio como ruta y no hay host que validar.
    """
    texto = str(www or "").strip()
    if not texto:
        return ""
    if "://" in texto:
        return texto
    return f"https://{texto}"


# ----------------------------------------------------------------------
# Las defensas
# ----------------------------------------------------------------------

def _es_direccion_interna(ip_texto: str) -> bool:
    """
    Si la IP apunta a algo que no debería alcanzarse desde fuera.

    `is_reserved` incluye `169.254.169.254`, el endpoint de metadatos que en
    varios proveedores de nube entrega credenciales a quien sepa pedirlas.
    """
    try:
        ip = ipaddress.ip_address(ip_texto)
    except ValueError:
        return True  # lo que no se puede evaluar, no se visita
    return bool(ip.is_private or ip.is_loopback or ip.is_link_local
                or ip.is_reserved or ip.is_multicast or ip.is_unspecified)


def _direcciones_de(host: str, puerto: int) -> List[str]:
    """Todas las direcciones del host. Vacío si el DNS no resuelve."""
    try:
        registros = socket.getaddrinfo(host, puerto, proto=socket.IPPROTO_TCP)
    except (socket.gaierror, UnicodeError, ValueError):
        return []
    return [r[4][0] for r in registros]


def destino_permitido(url: str, resolver: Optional[Callable[[str, int], List[str]]] = None
                      ) -> Tuple[bool, str]:
    """
    `(True, "")` si la URL se puede visitar; `(False, motivo)` si no.

    `resolver` se inyecta para poder probar el rechazo de una IP interna sin
    depender de que exista un dominio que resuelva a ella.
    """
    partes = urllib.parse.urlparse(url)
    if partes.scheme.lower() not in ESQUEMAS_PERMITIDOS:
        return (False, MOTIVO_ESQUEMA)
    if not partes.hostname:
        return (False, MOTIVO_SIN_HOST)

    puerto = partes.port or (443 if partes.scheme.lower() == "https" else 80)
    direcciones = (resolver or _direcciones_de)(partes.hostname, puerto)
    if not direcciones:
        return (False, MOTIVO_DNS)
    # **Todas**, no la primera: un host con dos registros A —uno público y uno
    # interno— pasaría revisando solo uno.
    if any(_es_direccion_interna(ip) for ip in direcciones):
        return (False, MOTIVO_DESTINO_INTERNO)
    return (True, "")


class _SinRedireccionesAutomaticas(urllib.request.HTTPRedirectHandler):
    """
    Apaga el seguimiento automático: `urllib` levanta `HTTPError` en cada 3xx.

    Es lo que permite revalidar el destino en cada salto. Con el manejador por
    defecto, un `301` hacia `http://169.254.169.254` se sigue solo y la
    comprobación inicial no sirve de nada.
    """

    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return None


def _abrir(url: str):
    """Una sola petición, sin seguir redirecciones, con `User-Agent` propio."""
    peticion = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
    opener = urllib.request.build_opener(_SinRedireccionesAutomaticas)
    return opener.open(peticion, timeout=TIEMPO_ESPERA_S)


def _leer_acotado(respuesta) -> bytes:
    """Como mucho `TECHO_LECTURA_BYTES`. Un servidor sin fin no tumba la función."""
    return respuesta.read(TECHO_LECTURA_BYTES)


# ----------------------------------------------------------------------
# HTML -> texto
# ----------------------------------------------------------------------

class _TextoDeHtml(HTMLParser):
    """Extrae el texto visible. `script`, `style` y `noscript` no son contenido."""

    IGNORADAS = frozenset({"script", "style", "noscript", "template"})

    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.partes: List[str] = []
        self._silencio = 0

    def handle_starttag(self, tag, attrs):
        if tag in self.IGNORADAS:
            self._silencio += 1

    def handle_endtag(self, tag):
        if tag in self.IGNORADAS and self._silencio:
            self._silencio -= 1

    def handle_data(self, data):
        if not self._silencio and data.strip():
            self.partes.append(data.strip())


def texto_de_html(html: str) -> str:
    """El texto visible, con los espacios colapsados."""
    lector = _TextoDeHtml()
    try:
        lector.feed(html)
    # HTML roto es la norma en estos sitios, no la excepción.
    except Exception:
        pass
    return " ".join(" ".join(lector.partes).split())


def _decodificar(crudo: bytes, respuesta) -> str:
    """El charset que declare la respuesta; si miente, se leen los bytes igual."""
    codificacion = (getattr(respuesta, "headers", None)
                    and respuesta.headers.get_content_charset()) or "utf-8"
    return crudo.decode(codificacion, errors="replace")


# ----------------------------------------------------------------------
# robots.txt
# ----------------------------------------------------------------------

def _robots_permite(url: str, abrir: Callable[[str], Any]) -> bool:
    """
    Si `robots.txt` deja leer esta URL.

    Se descarga por el **mismo camino guardado** que el resto y se parsea con
    `RobotFileParser.parse`. El `RobotFileParser.read()` de la biblioteca abre la
    URL por su cuenta, sin timeout y sin ninguna de las comprobaciones de arriba:
    usarlo abriría un segundo agujero SSRF al lado del que acabamos de tapar.

    Si `robots.txt` no existe o no se puede leer, se permite — es lo que dice el
    estándar y lo que hace cualquier rastreador.
    """
    partes = urllib.parse.urlparse(url)
    destino = f"{partes.scheme}://{partes.netloc}/robots.txt"
    try:
        with abrir(destino) as respuesta:
            texto = _decodificar(_leer_acotado(respuesta), respuesta)
    except Exception:
        return True

    lector = urllib.robotparser.RobotFileParser()
    lector.parse(texto.splitlines())
    return lector.can_fetch(USER_AGENT, url)


# ----------------------------------------------------------------------
# Lo que consume el agente
# ----------------------------------------------------------------------

def _fallo(motivo: str, mensaje: str) -> Dict[str, Any]:
    return {"success": False, "motivo": motivo, "message": mensaje, "texto": ""}


def _siguiente_salto(error: urllib.error.HTTPError, actual: str) -> Optional[str]:
    """La URL del `Location` de un 3xx, absoluta. `None` si no hay."""
    destino = error.headers.get("Location") if error.headers else None
    return urllib.parse.urljoin(actual, destino) if destino else None


def extraer_texto(www: Any, abrir: Optional[Callable[[str], Any]] = None,
                  resolver: Optional[Callable[[str, int], List[str]]] = None
                  ) -> Dict[str, Any]:
    """
    El texto del sitio del negocio, o el motivo de no haberlo podido leer.

    `abrir` y `resolver` se inyectan —igual que `plano.generar_plano` recibe su
    `llm`— para que las pruebas ejerzan las defensas sin salir a la red. En
    producción se usan los de la biblioteca estándar.

    Nunca lanza. Un sitio caído, un `robots.txt` que prohíbe o una redirección
    hacia la red interna son resultados normales de este trabajo: 1 de cada 4
    sitios del DENUE falló en la medición de §2.3.
    """
    url = normalizar_url(www)
    if not url:
        return _fallo(MOTIVO_SIN_HOST, "El establecimiento no declaró sitio web.")

    abridor = abrir or _abrir
    for _ in range(MAXIMO_REDIRECCIONES + 1):
        permitido, motivo = destino_permitido(url, resolver)
        if not permitido:
            return _fallo(motivo, f"No se visita {url}: {motivo}.")
        if not _robots_permite(url, abridor):
            return _fallo(MOTIVO_ROBOTS, f"El robots.txt de {url} no permite leerla.")

        try:
            with abridor(url) as respuesta:
                crudo = _leer_acotado(respuesta)
                texto = texto_de_html(_decodificar(crudo, respuesta))
            return _resultado_del_texto(texto, url)
        except urllib.error.HTTPError as error:
            salto = _siguiente_salto(error, url)
            if salto is None:
                return _fallo(MOTIVO_HTTP, f"{url} respondió {error.code}.")
            url = salto
        except Exception as error:
            return _fallo(MOTIVO_RED, f"No se pudo leer {url}: {error}")

    return _fallo(MOTIVO_REDIRECCIONES, f"Demasiadas redirecciones desde {www}.")


def _resultado_del_texto(texto: str, url: str) -> Dict[str, Any]:
    """
    Texto útil o "no hay". El sitio que devuelve 16 caracteres no es un éxito.

    Distinguirlo importa: con `success: true` y texto vacío, el agente redacta
    un análisis sobre nada y lo presenta como si hubiera leído la página.
    """
    if len(texto) < MINIMO_UTIL_CHARS:
        return _fallo(MOTIVO_TEXTO_INSUFICIENTE,
                      f"{url} devolvió {len(texto)} caracteres: su contenido lo arma JavaScript.")
    return {"success": True, "motivo": "", "message": "", "texto": texto, "url": url}
