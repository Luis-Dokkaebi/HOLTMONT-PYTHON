"""
Cerrar una tarea y subir su evidencia.

Dos reportes del mismo día, que resultaron ser el mismo camino roto:

    BUG-0009 · CARLOS_MENDEZ (2026-08-18 13:59)
    «no me deja cerrar tareas que capture ni cargar archivos "pesados"»

    BUG-0010 · ROCIO_CASTRO (2026-08-18 19:42)
    «me marca q no subo archivo al correo para cerrar una tarea»

Son dos defectos encadenados:

1. **La puerta de cierre pedía tres evidencias, no una.**
   `validateCompletionFiles` (index.html) exigía `ARCHIVO` y además empujaba
   `CORREO` y `CARPETA` a la lista de obligatorios. Las tres columnas existen
   en el tracker general, así que cerrar al 100% pedía tres subidas distintas
   y bastaba que faltara una para contestar «Falta subir archivos a CORREO
   para poder dar 100%» — la frase exacta del reporte de ROCIO_CASTRO. Una
   tarea que no se resolvió por correo no tiene qué poner ahí: no había forma
   de cerrarla. La Política de Registro §3.4 pide evidencia, en singular.

2. **Los archivos grandes no llegaban nunca.**
   El adjunto viajaba como data URL dentro del JSON de `/api/legacy/upload`,
   y ese JSON es el cuerpo de una función serverless que la plataforma corta
   en 4.5 MB. Base64 infla 4/3, así que todo lo que pasara de ~3.3 MB moría
   con un 413 de la plataforma —sin cuerpo JSON— mientras `index.html`
   anunciaba 35 MB. Encima ninguno de los selectores de archivo ponía
   `withFailureHandler`, así que el rechazo solo salía por consola: el
   spinner se quedaba girando. Eso es «no me deja cargar archivos pesados».

Y encadenados de verdad: sin poder subir el archivo tampoco se podía llenar
la columna que la puerta exigía, así que el primer defecto convertía al
segundo en un bloqueo de cierre.

El arreglo, en las dos capas:

* la puerta pide UNA evidencia entre `ARCHIVO`, `CORREO` y `CARPETA` en el
  tracker general (ventas conserva su expediente por documento);
* los archivos suben **directo a Storage** con una URL firmada
  (`/api/legacy/uploadUrl`), sin pasar por el cuerpo de la función; la ruta
  vieja en base64 sigue existiendo con su tope real declarado y un mensaje
  que dice qué hacer.
"""

from __future__ import annotations

import base64
import json
import os
import re
import shutil
import subprocess
from datetime import datetime

import pytest

from api.services import storage

RAIZ = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
INDEX = os.path.join(RAIZ, "index.html")
ADAPTADOR = os.path.join(RAIZ, "api_service.js")


def _leer(ruta: str) -> str:
    with open(ruta, encoding="utf-8") as fh:
        return fh.read()


# ---------------------------------------------------------------------------
# 1. La puerta de cierre: una evidencia basta
# ---------------------------------------------------------------------------

# Encabezados del tracker general tal como los pinta la vista: las tres
# columnas de archivo conviven, que es justo lo que disparaba el bloqueo.
ENCABEZADOS_TRACKER = ["FOLIO", "CONCEPTO", "RESPONSABLE", "AVANCE", "ESTATUS",
                       "CUMPLIMIENTO", "ARCHIVO", "CORREO", "CARPETA"]
ENCABEZADOS_VENTAS = ["FOLIO", "CLIENTE", "AVANCE", "INFO CLIENTE", "F2",
                      "COTIZACION", "TIMELINE", "LAYOUT", "CORREO", "CARPETA"]

# (fila, encabezados, veredicto esperado). `missing` se compara completo
# porque es el texto que la persona acaba leyendo.
CASOS_DE_CIERRE = [
    # El reporte de ROCIO_CASTRO: evidencia en CARPETA, nada en CORREO.
    ({"AVANCE": "100%", "CARPETA": "https://storage/x.pdf"}, ENCABEZADOS_TRACKER,
     {"valid": True}),
    # El mismo caso al revés: el correo alcanza sin carpeta.
    ({"AVANCE": "100%", "CORREO": "https://storage/x.pdf"}, ENCABEZADOS_TRACKER,
     {"valid": True}),
    ({"AVANCE": "100%", "ARCHIVO": "https://storage/x.pdf"}, ENCABEZADOS_TRACKER,
     {"valid": True}),
    # Cerrar sin ninguna evidencia sigue bloqueado: §3.4 pide una.
    ({"AVANCE": "100%"}, ENCABEZADOS_TRACKER,
     {"valid": False, "missing": "ARCHIVO o CORREO o CARPETA"}),
    # Un espacio en blanco no es una evidencia.
    ({"CUMPLIMIENTO": "SI", "ARCHIVO": "   "}, ENCABEZADOS_TRACKER,
     {"valid": False, "missing": "ARCHIVO o CORREO o CARPETA"}),
    # Estatus terminal es cierre igual que el 100%.
    ({"ESTATUS": "TERMINADO", "CORREO": "https://storage/x.pdf"}, ENCABEZADOS_TRACKER,
     {"valid": True}),
    # A media tarea no se pide nada.
    ({"AVANCE": "50"}, ENCABEZADOS_TRACKER, {"valid": True}),
    # Ventas conserva su expediente completo...
    ({"AVANCE": "100", "INFO CLIENTE": "u", "F2": "u", "COTIZACION": "u",
      "TIMELINE": "u", "LAYOUT": "u"}, ENCABEZADOS_VENTAS, {"valid": True}),
    ({"AVANCE": "100", "INFO CLIENTE": "u", "F2": "", "COTIZACION": "u",
      "TIMELINE": "u", "LAYOUT": "u"}, ENCABEZADOS_VENTAS,
     {"valid": False, "missing": "F2"}),
    # ...pero tampoco ahí se exigen CORREO y CARPETA: el expediente son los
    # cinco documentos del proceso de cotización, no siete.
    ({"AVANCE": "100", "INFO CLIENTE": "u", "F2": "u", "COTIZACION": "u",
      "TIMELINE": "u", "LAYOUT": "u", "CORREO": "", "CARPETA": ""},
     ENCABEZADOS_VENTAS, {"valid": True}),
    # Una hoja sin columnas de archivo no puede exigir lo que no tiene dónde
    # capturarse (mismo criterio que el control de alta).
    ({"AVANCE": "100%"}, ["FOLIO", "CONCEPTO", "AVANCE"], {"valid": True}),
]


def _veredictos_de_la_vista(tmp_path) -> list:
    """Corre la regla real de `index.html` en node y devuelve sus veredictos."""
    html = _leer(INDEX)
    inicio = html.index("// === INICIO REGLA DE EVIDENCIA")
    fin = html.index("// === FIN REGLA DE EVIDENCIA")

    casos = [[fila, encabezados] for fila, encabezados, _ in CASOS_DE_CIERRE]
    guion = tmp_path / "regla_evidencia.js"
    guion.write_text(
        html[inicio:fin]
        + f"\nconsole.log(JSON.stringify({json.dumps(casos)}"
        + ".map(function (caso) { return validateCompletionFiles(caso[0], caso[1]); })));",
        encoding="utf-8")

    salida = subprocess.run(["node", str(guion)], capture_output=True, text=True, check=True)
    return json.loads(salida.stdout)


@pytest.mark.skipif(not shutil.which("node"), reason="node no está instalado")
def test_la_puerta_de_cierre_da_los_veredictos_esperados(tmp_path):
    esperado = [veredicto for _, _, veredicto in CASOS_DE_CIERRE]
    assert _veredictos_de_la_vista(tmp_path) == esperado


def test_la_vista_ya_no_exige_correo_y_carpeta_ademas_del_archivo():
    """
    La regresión concreta: `requiredFiles.push('CORREO', 'CARPETA')` convertía
    dos columnas opcionales en obligatorias para todo cierre.
    """
    html = _leer(INDEX)
    assert "requiredFiles.push('CORREO', 'CARPETA')" not in html


def test_el_aviso_de_cierre_dice_que_basta_una_evidencia():
    """
    El texto viejo («Falta subir archivos a CORREO para poder dar 100%») le
    pedía a la persona algo que no podía cumplir. El nuevo nombra las tres
    columnas y dice que con una alcanza.
    """
    html = _leer(INDEX)
    assert "sube al menos un archivo en" in html
    assert "Swal.fire('Archivos incompletos'" not in html


# ---------------------------------------------------------------------------
# 2. La subida: la ruta JSON declara su tope real
# ---------------------------------------------------------------------------

class _AlmacenFalso:
    def __init__(self, firma=None):
        self.subidas = []
        self.firmadas = []
        self._firma = firma if firma is not None else {
            "signed_url": "https://supabase.local/storage/v1/object/upload/sign/archivos/RUTA?token=T",
            "token": "T",
        }

    def from_(self, nombre_bucket):
        self._bucket = nombre_bucket
        return self

    def upload(self, ruta, contenido, opciones):
        self.subidas.append((self._bucket, ruta, contenido, opciones))

    def create_signed_upload_url(self, ruta):
        self.firmadas.append((self._bucket, ruta))
        return self._firma

    def get_public_url(self, ruta):
        return f"https://supabase.local/storage/v1/object/public/{self._bucket}/{ruta}"


class _ClienteFalso:
    def __init__(self, firma=None):
        self.storage = _AlmacenFalso(firma)


class _ManagerFalso:
    is_configured = True

    def __init__(self, firma=None):
        self.client = _ClienteFalso(firma)


def _data_url(contenido: bytes, mime: str = "application/pdf") -> str:
    return f"data:{mime};base64,{base64.b64encode(contenido).decode()}"


def test_la_ruta_json_no_promete_mas_de_lo_que_cabe_en_el_cuerpo():
    """
    El tope declarado tiene que caber en el cuerpo que admite la plataforma
    **después** de inflarlo a base64 (4/3). Si esta cuenta deja de dar, el
    usuario vuelve a recibir un 413 sin mensaje.
    """
    assert storage.MAX_BYTES_SUBIDA_JSON * 4 / 3 < storage.LIMITE_CUERPO_FUNCION


def test_un_archivo_pesado_por_la_ruta_json_se_rechaza_con_instrucciones(monkeypatch):
    """
    Antes esto no lo rechazaba nadie: el 413 lo emitía la plataforma sin JSON
    y el navegador se quedaba sin mensaje que mostrar.
    """
    falso = _ManagerFalso()
    monkeypatch.setattr("api.services.supabase_manager.sb_manager", falso)
    monkeypatch.setattr(storage, "MAX_BYTES_SUBIDA_JSON", 10)

    resultado = storage.subir(_data_url(b"x" * 100), "application/pdf", "plano.pdf")

    assert resultado["success"] is False
    assert "URL firmada" in resultado["message"]
    assert falso.client.storage.subidas == [], "no debe escribir nada al rechazar"


def test_un_archivo_chico_sigue_subiendo_por_la_ruta_json(monkeypatch):
    falso = _ManagerFalso()
    monkeypatch.setattr("api.services.supabase_manager.sb_manager", falso)

    resultado = storage.subir(_data_url(b"contenido"), "application/pdf", "plano.pdf")

    assert resultado["success"] is True
    assert falso.client.storage.subidas[0][2] == b"contenido"


# ---------------------------------------------------------------------------
# 3. La subida directa: los bytes no pasan por la función
# ---------------------------------------------------------------------------

def test_la_url_firmada_trae_destino_y_url_publica(monkeypatch):
    falso = _ManagerFalso()
    monkeypatch.setattr("api.services.supabase_manager.sb_manager", falso)

    resultado = storage.url_de_subida_firmada("plano final.pdf", cliente="ACME INDUSTRIAL")

    assert resultado["success"] is True
    assert resultado["uploadUrl"].startswith("https://supabase.local/")
    # La URL pública es la que se guarda en la celda: tiene que apuntar a la
    # misma clave que se firmó, o la fila quedaría con un enlace muerto.
    assert resultado["path"] in resultado["fileUrl"]
    assert "ACME INDUSTRIAL" in resultado["path"]
    assert resultado["maxBytes"] == storage.MAX_BYTES_SUBIDA_DIRECTA


def test_la_ruta_firmada_la_decide_el_servidor(monkeypatch):
    """
    Firmar la clave que mande el navegador dejaría escribir en cualquier parte
    del bucket. La ruta se arma con `ruta_de_archivo`, igual que en `subir()`.
    """
    falso = _ManagerFalso()
    monkeypatch.setattr("api.services.supabase_manager.sb_manager", falso)

    resultado = storage.url_de_subida_firmada("../../secreto.pdf")

    _, ruta = falso.client.storage.firmadas[0]
    assert ruta == resultado["path"]
    # AÑO/MES/archivo: el nombre que manda el cliente es un solo segmento y
    # pierde las barras, así que no puede salirse del prefijo del servidor.
    assert ruta.count("/") == 2
    assert ruta.startswith(f"{datetime.now().year}/")


def test_sin_supabase_la_subida_directa_lo_dice(monkeypatch):
    class _SinConfigurar:
        is_configured = False

    monkeypatch.setattr("api.services.supabase_manager.sb_manager", _SinConfigurar())
    resultado = storage.url_de_subida_firmada("plano.pdf")

    assert resultado["success"] is False
    assert "no está configurado" in resultado["message"]


def test_si_storage_no_devuelve_url_firmada_no_se_finge_exito(monkeypatch):
    monkeypatch.setattr("api.services.supabase_manager.sb_manager", _ManagerFalso(firma={}))
    resultado = storage.url_de_subida_firmada("plano.pdf")

    assert resultado["success"] is False
    assert "URL firmada" in resultado["message"]


# ---------------------------------------------------------------------------
# 4. El camino completo: vista -> adaptador -> endpoint
# ---------------------------------------------------------------------------

def test_el_adaptador_sube_directo_a_storage():
    js = _leer(ADAPTADOR)
    assert "subirArchivoDirecto" in js
    assert "/api/legacy/uploadUrl" in js
    # El PUT lleva el archivo tal cual: si volviera a mandarse en base64
    # dentro de un JSON, el tope de 4.5 MB regresaría con él.
    assert "method: 'PUT'" in js


def test_la_vista_sube_por_una_sola_puerta():
    """
    Los selectores de archivo (celda del tracker, adjunto general y validación
    de diseño) pasan por `subirArchivoAlmacen`, que es donde vive el manejo de
    errores. Llamar a `uploadFileToDrive` por fuera es volver al camino sin
    `withFailureHandler`, que es como el fallo se volvía invisible.
    """
    html = _leer(INDEX)
    inicio = html.index("// === INICIO SUBIDA DE ARCHIVOS")
    fin = html.index("// === FIN SUBIDA DE ARCHIVOS")
    fuera = html[:inicio] + html[fin:]

    assert "uploadFileToDrive" not in fuera
    assert fuera.count("subirArchivoAlmacen(file") == 3


def test_el_fallo_de_subida_se_le_muestra_a_la_persona():
    html = _leer(INDEX)
    assert html.count("No se subió el archivo") == 3


@pytest.mark.skipif(not shutil.which("node"), reason="node no está instalado")
def test_los_scripts_de_index_html_compilan(tmp_path):
    """
    Puerta de sintaxis para el monolito del frontend.

    Al escribir este arreglo se declaró un `valorDeColumna` que ya existía 1.300
    líneas más arriba. Es un `SyntaxError` de redeclaración: el bloque entero no
    se evalúa, Vue no monta y la pantalla queda en blanco — y ninguna prueba que
    lea `index.html` como texto lo ve. Node sí.
    """
    html = _leer(INDEX)
    bloques = re.findall(r"<script(?![^>]*src=)[^>]*>(.*?)</script>", html, re.S)
    assert bloques, "no se encontró ningún script embebido en index.html"

    for numero, bloque in enumerate(bloques):
        guion = tmp_path / f"bloque_{numero}.js"
        guion.write_text(bloque, encoding="utf-8")
        revision = subprocess.run(["node", "--check", str(guion)],
                                  capture_output=True, text=True)
        assert revision.returncode == 0, (
            f"El bloque <script> #{numero} de index.html no compila:\n{revision.stderr}")
