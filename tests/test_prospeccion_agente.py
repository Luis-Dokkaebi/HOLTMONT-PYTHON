"""
El agente de prospección y el extractor web (Fase 4 del plan).

Dos módulos con dos razones distintas para existir esta suite:

**`extractor_web.py` es SSRF de manual.** Recibe una URL que viene del dato del
INEGI y, en el peor caso, del usuario, y la descarga desde el servidor. Un
servidor que descarga URLs ajenas es una puerta a lo que el atacante no alcanza:
`127.0.0.1`, la red privada del despliegue y `169.254.169.254`, el endpoint de
metadatos que en varias nubes entrega credenciales. Las pruebas de abajo son la
lista de §9 del plan, una por defensa, y **ninguna necesita red**: el abridor y
el resolutor se inyectan.

**`prospeccion_agente.py` decide qué se le dice a un tercero.** El texto que
produce acaba en un correo a un negocio real. Lo que se prueba no es que el LLM
escriba bien —eso no se puede probar— sino que el grafo elija bien la rama, que
declare de dónde salió el texto y que **no invente** cuando no hay con qué.

Todo con dobles en las fronteras (red, LLM, base) y ninguno en el núcleo.
"""

from __future__ import annotations

import io
from typing import Dict, List, Optional

import pytest

from api.services import extractor_web as ex
from api.services import prospeccion_agente as ag

ESTABLECIMIENTO = {
    "id": "9274655",
    "nom_estab": "FERRETERIA EL TORNILLO",
    "nombre_act": "Comercio al por menor en ferreterías y tlapalerías",
    "per_ocu": "0 a 5 personas",
    "telefono": "5512345678",
    "correoelec": "VENTAS@TORNILLO.MX",
    "www": "WWW.TORNILLO.MX",
    "municipio": "Cuauhtémoc",
    "latitud": 19.41887981,
    "longitud": -99.09012648,
}

SIN_SITIO = {**ESTABLECIMIENTO, "www": None}

# Texto largo de sobra para pasar el mínimo útil: lo que interesa de un sitio de
# ferretería es la lista de lo que vende.
PAGINA = (
    "<html><head><style>.a{color:red}</style></head><body>"
    "<script>window.x=1</script>"
    "<h1>Ferretería El Tornillo</h1>"
    "<p>Venta de tubería de cobre, conexiones, herramienta eléctrica, cemento, "
    "varilla, alambrón y material eléctrico para obra. Servicio a constructoras "
    "de la Ciudad de México desde 1994. Entregas en obra.</p>"
    "</body></html>"
)

PUBLICA = ["93.184.216.34"]


class _Respuesta(io.BytesIO):
    """Lo mínimo que `extraer_texto` usa de una respuesta de `urllib`."""

    def __init__(self, cuerpo: str, charset: str = "utf-8"):
        super().__init__(cuerpo.encode(charset))
        self.headers = _Cabeceras(charset)

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        self.close()
        return False


class _Cabeceras:
    def __init__(self, charset: str):
        self._charset = charset

    def get_content_charset(self):
        return self._charset

    def get(self, clave, por_defecto=None):
        return por_defecto


def _abridor(paginas: Dict[str, str], registro: Optional[List[str]] = None):
    """Un abridor falso. Lo que no esté en `paginas` se comporta como un 404."""
    import urllib.error

    def abrir(url: str):
        if registro is not None:
            registro.append(url)
        if url not in paginas:
            raise urllib.error.HTTPError(url, 404, "Not Found", None, None)
        return _Respuesta(paginas[url])

    return abrir


def _resolutor(mapa: Dict[str, List[str]]):
    return lambda host, puerto: mapa.get(host, [])


# ----------------------------------------------------------------------
# Defensas contra SSRF (plan §9)
# ----------------------------------------------------------------------

@pytest.mark.parametrize("url", [
    "file:///etc/passwd",
    "ftp://archivos.internos/backup.zip",
    "gopher://127.0.0.1:6379/_FLUSHALL",
])
def test_solo_se_visitan_http_y_https(url):
    """
    `file:///etc/passwd` es la versión trivial de esto, y `gopher://` la que se
    usa para hablarle a un Redis interno.
    """
    permitido, motivo = ex.destino_permitido(url, _resolutor({}))
    assert permitido is False
    assert motivo == ex.MOTIVO_ESQUEMA


@pytest.mark.parametrize("ip", [
    "127.0.0.1",          # loopback
    "10.0.0.5",           # privada
    "192.168.1.1",        # privada
    "172.16.0.9",         # privada
    "169.254.169.254",    # metadatos de la nube: credenciales
    "0.0.0.0",            # sin especificar
    "::1",                # loopback IPv6
    "fd00::1",            # privada IPv6
])
def test_no_se_visita_ninguna_direccion_interna(ip):
    permitido, motivo = ex.destino_permitido(
        "https://negocio.mx/", _resolutor({"negocio.mx": [ip]}))
    assert permitido is False, f"{ip} no debería alcanzarse desde el servidor"
    assert motivo == ex.MOTIVO_DESTINO_INTERNO


def test_basta_una_direccion_interna_entre_varias_para_rechazar():
    """
    Un host con dos registros A —uno público y uno interno— pasaría si solo se
    mirara el primero. Es el rodeo más barato que existe contra esta defensa.
    """
    permitido, motivo = ex.destino_permitido(
        "https://negocio.mx/", _resolutor({"negocio.mx": ["93.184.216.34", "10.0.0.5"]}))
    assert permitido is False
    assert motivo == ex.MOTIVO_DESTINO_INTERNO


def test_un_host_publico_si_se_visita():
    assert ex.destino_permitido(
        "https://negocio.mx/", _resolutor({"negocio.mx": PUBLICA})) == (True, "")


def test_un_dominio_que_no_resuelve_no_se_visita():
    permitido, motivo = ex.destino_permitido("https://noexiste.mx/", _resolutor({}))
    assert (permitido, motivo) == (False, ex.MOTIVO_DNS)


def test_una_url_sin_host_no_se_visita():
    permitido, motivo = ex.destino_permitido("https:///solo-ruta", _resolutor({}))
    assert (permitido, motivo) == (False, ex.MOTIVO_SIN_HOST)


def test_una_redireccion_hacia_la_red_interna_se_corta_en_el_salto():
    """
    La comprobación inicial no ve un `301`. Con el seguimiento automático de
    `urllib`, un sitio público que redirige a `http://169.254.169.254` deja la
    primera defensa en nada — por eso el manejador está apagado y cada salto se
    revalida entero.
    """
    import urllib.error

    def abrir(url):
        if url.endswith("/robots.txt"):
            raise urllib.error.HTTPError(url, 404, "Not Found", None, None)
        error = urllib.error.HTTPError(url, 301, "Moved", None, None)
        error.headers = {"Location": "http://169.254.169.254/latest/meta-data/"}
        raise error

    salida = ex.extraer_texto(
        "https://negocio.mx/",
        abrir=abrir,
        resolver=_resolutor({"negocio.mx": PUBLICA, "169.254.169.254": ["169.254.169.254"]}))
    assert salida["success"] is False
    assert salida["motivo"] == ex.MOTIVO_DESTINO_INTERNO


def test_una_cadena_de_redirecciones_no_da_vueltas_para_siempre():
    import urllib.error

    def abrir(url):
        if url.endswith("/robots.txt"):
            raise urllib.error.HTTPError(url, 404, "Not Found", None, None)
        error = urllib.error.HTTPError(url, 302, "Found", None, None)
        error.headers = {"Location": "https://negocio.mx/otra"}
        raise error

    salida = ex.extraer_texto("https://negocio.mx/", abrir=abrir,
                              resolver=_resolutor({"negocio.mx": PUBLICA}))
    assert salida["motivo"] == ex.MOTIVO_REDIRECCIONES


def test_se_respeta_el_robots_txt_del_sitio():
    paginas = {
        "https://negocio.mx/robots.txt": "User-agent: *\nDisallow: /",
        "https://negocio.mx/": PAGINA,
    }
    salida = ex.extraer_texto("https://negocio.mx/", abrir=_abridor(paginas),
                              resolver=_resolutor({"negocio.mx": PUBLICA}))
    assert salida["success"] is False
    assert salida["motivo"] == ex.MOTIVO_ROBOTS


def test_sin_robots_txt_se_lee_igual():
    """Es lo que dice el estándar y lo que hace cualquier rastreador."""
    salida = ex.extraer_texto("https://negocio.mx/",
                              abrir=_abridor({"https://negocio.mx/": PAGINA}),
                              resolver=_resolutor({"negocio.mx": PUBLICA}))
    assert salida["success"] is True


def test_el_robots_txt_se_pide_por_el_mismo_camino_guardado():
    """
    `RobotFileParser.read()` abre la URL por su cuenta, sin timeout y sin
    ninguna de estas comprobaciones: usarlo abriría un segundo agujero SSRF al
    lado del que se acaba de tapar.
    """
    visitadas: List[str] = []
    ex.extraer_texto("https://negocio.mx/",
                     abrir=_abridor({"https://negocio.mx/": PAGINA}, visitadas),
                     resolver=_resolutor({"negocio.mx": PUBLICA}))
    assert visitadas[0] == "https://negocio.mx/robots.txt"


def test_la_lectura_tiene_techo_de_bytes():
    """Sin techo, un servidor que escupe bytes sin parar agota la función."""
    enorme = "<p>" + ("dato " * 200_000) + "</p>"
    salida = ex.extraer_texto("https://negocio.mx/",
                              abrir=_abridor({"https://negocio.mx/": enorme}),
                              resolver=_resolutor({"negocio.mx": PUBLICA}))
    assert salida["success"] is True
    assert len(salida["texto"]) <= ex.TECHO_LECTURA_BYTES


def test_el_user_agent_es_identificable():
    """Quien vea este agente en sus registros tiene que saber a quién reclamar."""
    assert "Holtmont" in ex.USER_AGENT
    assert "http" in ex.USER_AGENT


# ----------------------------------------------------------------------
# HTML -> texto
# ----------------------------------------------------------------------

def test_el_texto_extraido_no_incluye_scripts_ni_estilos():
    texto = ex.texto_de_html(PAGINA)
    assert "window.x" not in texto
    assert "color:red" not in texto
    assert "tubería de cobre" in texto


def test_un_html_roto_no_tumba_la_extraccion():
    """El HTML de la mitad de estos sitios es de 2003. Es la norma, no el caso raro."""
    assert "Hola" in ex.texto_de_html("<p>Hola<div><span>mundo")


def test_un_sitio_que_arma_su_contenido_con_js_no_cuenta_como_exito():
    """
    `WWW.ADTEC.COM.MX` devolvió 16 caracteres en la medición de §2.3: el HTML
    llega y el contenido lo pone el navegador. Con `success: true` y texto
    vacío, el agente analizaría la nada y lo presentaría como si hubiera leído
    la página.
    """
    salida = ex.extraer_texto("https://negocio.mx/",
                              abrir=_abridor({"https://negocio.mx/": "<html><body>Inicio</body></html>"}),
                              resolver=_resolutor({"negocio.mx": PUBLICA}))
    assert salida["success"] is False
    assert salida["motivo"] == ex.MOTIVO_TEXTO_INSUFICIENTE


def test_un_sitio_caido_se_reporta_sin_lanzar():
    """1 de cada 4 sitios del DENUE falló en la medición: es un resultado normal."""
    salida = ex.extraer_texto("https://negocio.mx/", abrir=_abridor({}),
                              resolver=_resolutor({"negocio.mx": PUBLICA}))
    assert salida["success"] is False
    assert salida["motivo"] == ex.MOTIVO_HTTP


@pytest.mark.parametrize("crudo,esperado", [
    ("WWW.GRUPOLAFE.COM", "https://WWW.GRUPOLAFE.COM"),
    ("norsk.mx", "https://norsk.mx"),
    ("http://ya.tiene.mx", "http://ya.tiene.mx"),
    ("https://ya.tiene.mx", "https://ya.tiene.mx"),
    ("", ""),
    (None, ""),
])
def test_se_antepone_el_esquema_que_el_denue_no_trae(crudo, esperado):
    """Solo 10 de las 2,848 URLs del DENUE traen esquema (§2.4)."""
    assert ex.normalizar_url(crudo) == esperado


def test_un_establecimiento_sin_sitio_lo_dice_sin_salir_a_la_red():
    salida = ex.extraer_texto(None)
    assert salida["motivo"] == ex.MOTIVO_SIN_HOST


# ----------------------------------------------------------------------
# El agente: de dónde sale el texto y qué rama toma
# ----------------------------------------------------------------------

class LlmFalso:
    """Doble del LLM. Guarda los prompts: es lo que se verifica, no la prosa."""

    def __init__(self, respuesta: str = "TEXTO DEL MODELO"):
        self.respuesta = respuesta
        self.prompts: List[str] = []

    def invoke(self, prompt: str):
        self.prompts.append(prompt)
        return type("R", (), {"content": self.respuesta})()


def test_la_cache_es_la_primera_capa_y_evita_salir_a_la_red():
    """
    Es la capa más barata de las tres. Si se saltara, cada consulta esperaría a
    un servidor ajeno con el vendedor mirando la pantalla.
    """
    llamadas = []
    salida = ag.ejecutar(ESTABLECIMIENTO, "tubería", llm=LlmFalso(),
                         cache=lambda i: "Venden tubería de cobre y conexiones para obra.",
                         extractor=lambda w: llamadas.append(w) or {"success": True, "texto": "x"})
    assert salida["fuente"] == ag.FUENTE_CACHE
    assert llamadas == [], "con caché no se sale a leer el sitio"


def test_sin_cache_se_lee_el_sitio_en_vivo():
    salida = ag.ejecutar(ESTABLECIMIENTO, "tubería", llm=LlmFalso(),
                         extractor=lambda w: {"success": True, "texto": "Venden tubería." * 20})
    assert salida["fuente"] == ag.FUENTE_WEB
    assert salida["tipo"] == ag.TIPO_ANALISIS


def test_si_el_sitio_no_da_texto_se_cae_a_tavily():
    """
    Es el caso de las páginas que arman su contenido con JavaScript — 1 de cada
    4 en la medición de §2.3. Tavily es la tercera capa, no la primera.
    """
    salida = ag.ejecutar(ESTABLECIMIENTO, "tubería", llm=LlmFalso(),
                         extractor=lambda w: {"success": False, "texto": ""},
                         buscador=lambda q: [{"content": "Ferretería con servicio a obra."}])
    assert salida["fuente"] == ag.FUENTE_TAVILY


def test_sin_sitio_el_grafo_va_directo_a_redactar():
    """
    Solo el 13.6% de los establecimientos declaró web. La rama de redacción es
    el caso normal, no la excepción.
    """
    salida = ag.ejecutar(SIN_SITIO, "cemento", llm=LlmFalso())
    assert salida["fuente"] == ag.FUENTE_SIN_WEB
    assert salida["tipo"] == ag.TIPO_CORREO


def test_el_orden_de_las_capas_es_el_del_costo():
    """Caché antes que lectura, y lectura antes que Tavily. En ese orden."""
    visitados: List[str] = []
    ag.nodo_sitio(
        {"establecimiento": ESTABLECIMIENTO},
        cache=lambda i: visitados.append("cache") or "",
        extractor=lambda w: visitados.append("web") or {"success": False},
        buscador=lambda q: visitados.append("tavily") or [])
    assert visitados == ["cache", "web", "tavily"]


def test_lo_leido_en_vivo_se_guarda_en_la_cache():
    """Para que la siguiente consulta sobre ese negocio no vuelva a salir."""
    guardado: List[tuple] = []
    ag.ejecutar(ESTABLECIMIENTO, "x", llm=LlmFalso(),
                extractor=lambda w: {"success": True, "texto": "Texto del sitio." * 20},
                guardar_cache=lambda i, t: guardado.append((i, t)))
    assert guardado and guardado[0][0] == "9274655"


def test_que_falle_la_cache_no_tumba_al_agente():
    """
    La caché es un lujo, no el trabajo. Si la base no responde, el vendedor
    tiene que recibir su análisis igual.
    """
    def cache_rota(_):
        raise RuntimeError("la base no responde")

    salida = ag.ejecutar(ESTABLECIMIENTO, "x", llm=LlmFalso(), cache=cache_rota,
                         extractor=lambda w: {"success": True, "texto": "Venden tubería." * 20})
    assert salida["success"] is True
    assert salida["fuente"] == ag.FUENTE_WEB


def test_que_falle_tavily_no_tumba_al_agente():
    def buscador_roto(_):
        raise RuntimeError("sin crédito")

    salida = ag.ejecutar(ESTABLECIMIENTO, "x", llm=LlmFalso(),
                         extractor=lambda w: {"success": False}, buscador=buscador_roto)
    assert salida["success"] is True
    assert salida["fuente"] == ag.FUENTE_SIN_WEB


# ----------------------------------------------------------------------
# El agente: qué se le manda al modelo
# ----------------------------------------------------------------------

def test_el_analisis_lleva_el_texto_del_sitio_y_el_giro_del_inegi():
    llm = LlmFalso()
    ag.ejecutar(ESTABLECIMIENTO, "¿venden tubería de cobre?", llm=llm,
                cache=lambda i: "Catálogo: tubería de cobre tipo M y L, conexiones.")
    prompt = llm.prompts[0]
    assert "FERRETERIA EL TORNILLO" in prompt
    assert "tubería de cobre tipo M" in prompt
    assert "¿venden tubería de cobre?" in prompt


def test_el_correo_sin_sitio_no_lleva_un_bloque_de_contexto_vacio():
    """
    Con un "LO QUE DICE SU SITIO:" vacío, el modelo tiende a rellenarlo. Es la
    forma más limpia de inventar datos de un negocio real, y ese correo sale
    firmado por la empresa.
    """
    llm = LlmFalso()
    ag.ejecutar(SIN_SITIO, "cemento", llm=llm)
    assert "LO QUE DICE SU SITIO" not in llm.prompts[0]


def test_el_texto_del_sitio_se_recorta_antes_de_ir_al_modelo():
    """400 KB de texto no caben en la ventana de contexto y no hacen falta."""
    llm = LlmFalso()
    ag.ejecutar(ESTABLECIMIENTO, "x", llm=llm, cache=lambda i: "z" * 50_000)
    # Se mide la RACHA, no el total: la plantilla del prompt también tiene
    # alguna "z" suelta y contarlas todas daría un número que no es el recorte.
    assert "z" * ag.TECHO_CONTEXTO_CHARS in llm.prompts[0]
    assert "z" * (ag.TECHO_CONTEXTO_CHARS + 1) not in llm.prompts[0]


def test_sin_llm_no_se_fabrica_una_respuesta():
    """
    Un análisis inventado sin modelo es indistinguible de uno real para quien lo
    lee, y acaba en un correo a un tercero. Es el peor fallo posible aquí.
    """
    salida = ag.ejecutar(ESTABLECIMIENTO, "x", llm=None)
    assert salida["success"] is False
    assert "GROQ_API_KEY" in salida["message"]
    assert "texto" not in salida


def test_si_el_modelo_falla_se_dice_en_vez_de_reventar():
    class LlmCaido:
        def invoke(self, prompt):
            raise RuntimeError("429 rate limit")

    salida = ag.ejecutar(SIN_SITIO, "x", llm=LlmCaido())
    assert salida["success"] is False
    assert "429" in salida["message"]


def test_la_clave_de_groq_no_esta_escrita_en_el_codigo():
    """
    El notebook original trae una clave real en un comentario de la celda 4. Esa
    es la Fase 0 del plan; aquí se fija que no vuelva a pasar.
    """
    import pathlib

    fuente = pathlib.Path(ag.__file__).read_text(encoding="utf-8")
    assert "gsk_" not in fuente
    assert 'os.environ.get("GROQ_API_KEY")' in fuente


def test_sin_clave_de_groq_no_hay_llm(monkeypatch):
    monkeypatch.delenv("GROQ_API_KEY", raising=False)
    assert ag.llm_disponible() is None


def test_sin_clave_de_tavily_no_hay_buscador(monkeypatch):
    monkeypatch.delenv("TAVILY_API_KEY", raising=False)
    assert ag.buscador_disponible() is None


def test_el_extractor_siempre_esta_disponible():
    """Es biblioteca estándar: no depende de ninguna clave ni de ningún binario."""
    assert callable(ag.extractor_disponible())


def test_la_ruta_del_estado_es_la_bifurcacion_del_notebook():
    assert ag.ruta_despues_del_sitio({"texto_web": "algo"}) == "analizar"
    assert ag.ruta_despues_del_sitio({"texto_web": ""}) == "redactar"
    assert ag.ruta_despues_del_sitio({}) == "redactar"


def test_el_grafo_conserva_la_fuente_hasta_el_final():
    """
    Regresión real de esta fase. Con `StateGraph(dict)` el valor de retorno de
    un nodo REEMPLAZA el estado entero, así que `fuente` —que escribe el nodo
    del sitio— se perdía al correr el de análisis y la respuesta decía
    `sin_web` para un texto que venía de la caché. Falla en silencio: el
    análisis sale bien y solo miente la procedencia.
    """
    salida = ag.ejecutar(ESTABLECIMIENTO, "x", llm=LlmFalso(),
                         cache=lambda i: "Venden tubería de cobre para obra.")
    assert salida["fuente"] == ag.FUENTE_CACHE
    assert salida["texto"] == "TEXTO DEL MODELO"


# ----------------------------------------------------------------------
# La ruta HTTP
# ----------------------------------------------------------------------

_ESQUEMA_DENUE = """
CREATE TABLE denue (
  id TEXT PRIMARY KEY, nom_estab TEXT, nombre_act TEXT, codigo_act TEXT,
  per_ocu TEXT, telefono TEXT, correoelec TEXT, www TEXT,
  municipio TEXT, nom_vial TEXT, numero_ext TEXT, cod_postal TEXT,
  latitud REAL, longitud REAL
);
"""


@pytest.fixture
def cliente(tmp_path, monkeypatch):
    """Cliente con el catálogo apuntado a un SQLite de una fila y un LLM falso."""
    import sqlite3

    from fastapi.testclient import TestClient

    from api.main import app
    from api.services import denue_repo

    ruta = tmp_path / "denue.sqlite"
    conexion = sqlite3.connect(ruta)
    with conexion:
        conexion.executescript(_ESQUEMA_DENUE)
        conexion.execute(
            f"INSERT INTO denue VALUES ({', '.join('?' * 14)})",
            ("9274655", "FERRETERIA EL TORNILLO",
             "Comercio al por menor en ferreterías y tlapalerías", "467111",
             "0 a 5 personas", "5512345678", "VENTAS@TORNILLO.MX", "WWW.TORNILLO.MX",
             "Cuauhtémoc", "DONCELES", "10", "06010", 19.4188, -99.0901))
    conexion.close()

    monkeypatch.setattr(denue_repo, "RUTA_CATALOGO", ruta)
    monkeypatch.setattr(denue_repo, "_repositorio", None)
    # Sin red y sin clave: ni el LLM ni el extractor ni Tavily salen a ninguna
    # parte. Lo que se prueba aquí es el cableado de la ruta, no el modelo.
    monkeypatch.setattr(ag, "llm_disponible", lambda: LlmFalso("ANALISIS DEL MODELO"))
    monkeypatch.setattr(ag, "extractor_disponible",
                        lambda: (lambda w: {"success": True, "texto": "Venden tubería." * 20}))
    monkeypatch.setattr(ag, "buscador_disponible", lambda: None)
    with TestClient(app) as http:
        yield http
    monkeypatch.setattr(denue_repo, "_repositorio", None)


def test_la_ruta_del_agente_devuelve_el_analisis_y_su_procedencia(cliente):
    cuerpo = cliente.post("/api/geo/agente", json={
        "establecimiento_id": "9274655", "consulta": "¿venden tubería?"}).json()
    assert cuerpo["success"] is True
    assert cuerpo["tipo"] == ag.TIPO_ANALISIS
    assert cuerpo["texto"] == "ANALISIS DEL MODELO"
    assert cuerpo["fuente"] in (ag.FUENTE_CACHE, ag.FUENTE_WEB)


def test_la_ruta_del_agente_no_inventa_un_establecimiento_que_no_existe(cliente):
    """
    Con la ficha vacía, el correo saldría dirigido a "(sin nombre)" y con el
    giro en blanco. Mejor decir que ese id no está en el catálogo.
    """
    cuerpo = cliente.post("/api/geo/agente",
                          json={"establecimiento_id": "0", "consulta": "x"}).json()
    assert cuerpo["success"] is False
    assert "No existe el establecimiento" in cuerpo["message"]


def test_sin_clave_de_groq_la_ruta_degrada_sin_tumbar_el_modulo(cliente, monkeypatch):
    monkeypatch.setattr(ag, "llm_disponible", lambda: None)
    cuerpo = cliente.post("/api/geo/agente",
                          json={"establecimiento_id": "9274655"}).json()
    assert cuerpo["success"] is False
    assert "GROQ_API_KEY" in cuerpo["message"]


# ----------------------------------------------------------------------
# Los caminos de degradación, uno por uno
# ----------------------------------------------------------------------
#
# Son las ramas que solo corren cuando algo va mal: DNS que no resuelve, HTML
# que revienta el parser, la clave que no está. Cada una decide si el módulo
# degrada o se lleva por delante al resto, así que ninguna puede quedar sin
# ejercer.

def test_una_ip_ilegible_se_trata_como_interna():
    """Lo que no se puede evaluar, no se visita. Es el lado seguro del error."""
    assert ex._es_direccion_interna("no-es-una-ip") is True
    assert ex._es_direccion_interna("") is True


def test_una_ip_publica_no_es_interna():
    assert ex._es_direccion_interna("93.184.216.34") is False


def test_la_resolucion_real_devuelve_vacio_cuando_el_dominio_no_existe():
    """
    Sin red tampoco resuelve, que es justo el comportamiento que interesa: el
    extractor no puede lanzar por un dominio muerto.
    """
    assert ex._direcciones_de("no.existe.invalid", 443) == []


def test_la_resolucion_real_encuentra_el_loopback():
    """`localhost` resuelve sin salir a ningún lado, y el resultado es interno."""
    direcciones = ex._direcciones_de("localhost", 80)
    assert direcciones
    assert all(ex._es_direccion_interna(ip) for ip in direcciones)


def test_el_manejador_de_redirecciones_no_sigue_ninguna():
    """Devolver `None` es lo que hace que `urllib` levante el 3xx en vez de seguirlo."""
    manejador = ex._SinRedireccionesAutomaticas()
    assert manejador.redirect_request(None, None, 301, "Moved", {}, "http://otro") is None


def test_la_peticion_real_lleva_el_user_agent_y_el_timeout(monkeypatch):
    """
    El `User-Agent` identificable y el timeout son dos de las defensas de §9. Se
    comprueba sobre el abridor de producción, no sobre el doble.
    """
    capturado = {}

    class OpenerFalso:
        def open(self, peticion, timeout=None):
            capturado["ua"] = peticion.get_header("User-agent")
            capturado["timeout"] = timeout
            capturado["manejadores"] = True
            return "respuesta"

    monkeypatch.setattr(ex.urllib.request, "build_opener", lambda *a: OpenerFalso())
    assert ex._abrir("https://negocio.mx/") == "respuesta"
    assert capturado["ua"] == ex.USER_AGENT
    assert capturado["timeout"] == ex.TIEMPO_ESPERA_S


def test_un_html_que_revienta_el_parser_devuelve_lo_que_alcanzo_a_leer():
    """
    `HTMLParser.feed` no acepta bytes. Es el tipo de entrada que llega cuando un
    servidor declara mal su charset, y no puede tumbar la extracción.
    """
    assert ex.texto_de_html(b"<p>bytes</p>") == ""


def test_un_error_de_red_que_no_es_http_se_reporta_igual():
    """Un timeout o un certificado inválido no son `HTTPError`."""
    def abrir(url):
        raise TimeoutError("se agotó el tiempo de espera")

    salida = ex.extraer_texto("https://negocio.mx/", abrir=abrir,
                              resolver=_resolutor({"negocio.mx": PUBLICA}))
    assert salida["success"] is False
    assert salida["motivo"] == ex.MOTIVO_RED


def test_un_establecimiento_que_no_es_diccionario_no_revienta_el_prompt():
    """La ficha puede llegar vacía si el catálogo no está desplegado."""
    assert ag._campo(None, "nom_estab", "(sin nombre)") == "(sin nombre)"
    assert ag._campo("texto suelto", "nom_estab") == ""


def test_que_falle_escribir_la_cache_no_interrumpe_al_agente():
    """Guardar el texto es un lujo; entregar el análisis es el trabajo."""
    def guardar_roto(denue_id, texto):
        raise RuntimeError("la base rechazó la escritura")

    salida = ag.ejecutar(ESTABLECIMIENTO, "x", llm=LlmFalso(),
                         extractor=lambda w: {"success": True, "texto": "Venden tubería." * 20},
                         guardar_cache=guardar_roto)
    assert salida["success"] is True
    assert salida["fuente"] == ag.FUENTE_WEB


def test_con_clave_de_groq_se_construye_el_llm(monkeypatch):
    from api import paperclip_agents

    monkeypatch.setenv("GROQ_API_KEY", "clave-de-prueba")
    monkeypatch.setattr(paperclip_agents, "ChatGroq",
                        lambda **kwargs: f"LLM({kwargs['model']})")
    assert ag.llm_disponible() == f"LLM({ag.MODELO})"


def test_si_el_llm_no_se_puede_construir_se_devuelve_none(monkeypatch):
    """
    Una clave con formato inválido no puede tumbar el arranque: el resto del
    módulo —mapa, filtros, prospectos— no necesita el modelo.
    """
    from api import paperclip_agents

    def explota(**kwargs):
        raise ValueError("clave con formato inválido")

    monkeypatch.setenv("GROQ_API_KEY", "clave-rota")
    monkeypatch.setattr(paperclip_agents, "ChatGroq", explota)
    assert ag.llm_disponible() is None


def test_sin_el_paquete_de_groq_no_hay_llm(monkeypatch):
    from api import paperclip_agents

    monkeypatch.setenv("GROQ_API_KEY", "clave-de-prueba")
    monkeypatch.setattr(paperclip_agents, "ChatGroq", None)
    assert ag.llm_disponible() is None


def test_con_clave_de_tavily_se_construye_el_buscador(monkeypatch):
    monkeypatch.setenv("TAVILY_API_KEY", "clave-de-prueba")
    assert callable(ag.buscador_disponible())


def test_si_tavily_no_se_puede_construir_se_devuelve_none(monkeypatch):
    """Tavily es la tercera capa: sin ella el agente sigue con las dos primeras."""
    import builtins

    real = builtins.__import__

    def importar(nombre, *args, **kwargs):
        if "tavily" in nombre:
            raise ImportError("langchain_community no disponible")
        return real(nombre, *args, **kwargs)

    monkeypatch.setenv("TAVILY_API_KEY", "clave-de-prueba")
    monkeypatch.setattr(builtins, "__import__", importar)
    assert ag.buscador_disponible() is None
