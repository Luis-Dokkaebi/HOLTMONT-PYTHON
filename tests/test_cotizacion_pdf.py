"""La cotización se archiva en PDF con los documentos de la línea del tracker.

Pedido del dueño (2026-09-09):

    «Quiero que la cotización se transforme en un PDF y se guarde en los
    documentos de esa línea del tracker, en la sección de carpeta [...] es para
    que no se pierda toda la información que se va a trabajar.»

Lo que se pierde hoy: al guardar, la Pre Work Order reparte lo capturado entre
cinco tablas hijas (`wo_materiales`, `wo_herramientas`, `wo_mano_obra`,
`wo_equipos`, `wo_programa`) y ninguna pantalla las vuelve a juntar. Quien abre
la línea del tracker ve la tarea, no la cotización que la originó. El único
documento que recomponía todo era la nota de Obsidian, que en serverless dura
lo que dura el proceso.

Estas pruebas fijan las tres partes: que el PDF lleve de verdad lo capturado
(se lee el texto del PDF emitido, no se confía en que la función corrió), que
su URL se anexe a `archivoUrl` —la columna CARPETA de la fila, alias `carpeta`
en `backend/schemas/task.py`— sin borrar lo que subió una persona, y que un
fallo al archivar no se lleve por delante el guardado de la orden.
"""

from __future__ import annotations

import io
import os
import sys
from typing import Any, Dict
from unittest import mock

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from api.services import cotizacion_pdf  # noqa: E402

FOLIO = "1001AC Electro 090926"

ORDEN: Dict[str, Any] = {
    "cliente": "ACME INDUSTRIAL",
    "especialidad": "ELECTROMECANICA",
    "clasificacion": "AA",
    "prioridad": "AA - MEDIA PRIORIDAD",
    "responsable": "LUIS PEREYRA",
    "requisitor": "TERESA GARZA",
    "contacto": "compras@acme.mx",
    "TRABAJO": "MANTENIMIENTO",
    "concepto": "Muro de block de 10 x 3 m en nave industrial",
    "fechaCotizacion": "09/09/26",
    "archivoUrl": "https://drive.google.com/file/d/COTIZACION-DEL-CLIENTE/view",
    "materiales": [
        {"quantity": "450", "unit": "pza", "description": "Block hueco 15x20x40",
         "cost": "18.50", "total": 8325.0},
        {"quantity": "12", "unit": "bulto", "description": "Cemento gris",
         "cost": "220", "total": 2640.0},
        # La fila de ejemplo con la que arranca el formulario, en blanco.
        {"quantity": "", "unit": "", "description": "", "cost": "", "total": 0},
    ],
    "herramientas": [
        {"quantity": "1", "unit": "pza", "description": "Revolvedora de 1 saco",
         "cost": "850", "total": 850.0},
    ],
    "manoObra": [
        {"category": "Albañil", "salary": "2800", "personnel": "3", "weeks": "2",
         "unit": "semana", "total": 16800.0},
    ],
    "equipos": [
        {"quantity": "24", "unit": "dia", "description": "Andamio tubular",
         "days": "1", "cost": "120", "total": 2880.0},
    ],
    "programa": [
        {"seccion": "VISITA", "DESCRIPCION": "Levantamiento en sitio",
         "FECHA": "10/09/26", "RESPONSABLE": "TERESA GARZA", "TOTAL": 0},
        {"seccion": "TRABAJO", "DESCRIPCION": "Levantar muro",
         "FECHA": "15/09/26", "RESPONSABLE": "CUADRILLA 1", "TOTAL": 28855.0},
    ],
    "additionalCosts": {"insumos": 500, "viaticos": 0, "transporte": 1200},
}


def _texto_del_pdf(contenido: bytes) -> str:
    from pypdf import PdfReader

    lector = PdfReader(io.BytesIO(contenido))
    return "\n".join(pagina.extract_text() or "" for pagina in lector.pages)


# ----------------------------------------------------------------------
# 1. El PDF lleva lo que se capturó
# ----------------------------------------------------------------------

def test_el_pdf_es_un_pdf():
    contenido = cotizacion_pdf.construir_pdf(ORDEN, FOLIO)

    assert contenido[:5] == b"%PDF-"
    assert len(contenido) > 1000


def test_el_pdf_lleva_el_folio_y_la_cabecera_de_la_orden():
    texto = _texto_del_pdf(cotizacion_pdf.construir_pdf(ORDEN, FOLIO))

    assert FOLIO in texto
    assert "ACME INDUSTRIAL" in texto
    assert "TERESA GARZA" in texto
    assert "Muro de block" in texto


@pytest.mark.parametrize("esperado", [
    "MATERIALES REQUERIDOS", "Block hueco", "Cemento gris",
    "HERRAMIENTAS REQUERIDAS", "Revolvedora",
    "MANO DE OBRA", "Alba", "EQUIPO ESPECIAL", "Andamio",
    "PROGRAMA DEL PROYECTO", "Levantar muro", "CUADRILLA 1",
])
def test_el_pdf_lleva_las_tablas_de_la_cotizacion(esperado):
    """Lo que el dueño no quiere perder, bloque por bloque."""
    texto = _texto_del_pdf(cotizacion_pdf.construir_pdf(ORDEN, FOLIO))

    assert esperado in texto, f"'{esperado}' no aparece en el PDF"


def test_el_pdf_lleva_los_totales_con_los_que_se_cotiza():
    texto = _texto_del_pdf(cotizacion_pdf.construir_pdf(ORDEN, FOLIO))

    # 10,965.00 materiales + 850 herramienta + 16,800 mano de obra
    # + 2,880 equipo + 1,700 adicionales = 33,195.00; +15% = 38,174.25
    assert "$33,195.00" in texto
    assert "$38,174.25" in texto
    assert "GRAN TOTAL" in texto


def test_los_totales_del_formulario_ganan_a_los_calculados_aqui():
    """El tablero es la fuente de verdad del gran total: el PDF tiene que decir
    el mismo número que vio quien cotizó, no uno recalculado aparte."""
    orden = dict(ORDEN, totales={"subtotal": 40000, "utilidad": 6000, "total": 46000})

    texto = _texto_del_pdf(cotizacion_pdf.construir_pdf(orden, FOLIO))

    assert "$46,000.00" in texto
    assert "$38,174.25" not in texto


def test_la_fila_de_ejemplo_en_blanco_no_ensucia_el_documento():
    """El formulario arranca cada tabla con un renglón vacío; una fila de ceros
    en un documento que alguien lee para cotizar es ruido."""
    texto = _texto_del_pdf(cotizacion_pdf.construir_pdf(ORDEN, FOLIO))

    materiales = texto.split("MATERIALES REQUERIDOS")[1].split("HERRAMIENTAS")[0]
    assert materiales.count("$0.00") == 0


def test_una_orden_sin_tablas_sigue_emitiendo_su_pdf():
    """Una orden que aún no tiene estimación no debe reventar el guardado."""
    contenido = cotizacion_pdf.construir_pdf({"cliente": "ACME"}, FOLIO)

    texto = _texto_del_pdf(contenido)
    assert FOLIO in texto
    assert "GRAN TOTAL" in texto


def test_un_caracter_que_no_cabe_en_la_fuente_no_tumba_la_emision():
    """Helvetica es latin-1. Un emoji pegado en una descripción reventaría la
    emisión con `UnicodeEncodeError` y, con ella, el archivado de la orden."""
    orden = dict(ORDEN, concepto="Muro de block 🧱 en nave",
                 materiales=[{"quantity": "1", "unit": "pza",
                              "description": "Tornillo ✅ galvanizado",
                              "cost": "10", "total": 10}])

    texto = _texto_del_pdf(cotizacion_pdf.construir_pdf(orden, FOLIO))

    assert "Muro de block" in texto
    assert "Tornillo" in texto


def test_el_nombre_del_archivo_lleva_el_folio():
    assert cotizacion_pdf.nombre_de_archivo(FOLIO) == f"COTIZACION {FOLIO}.pdf"
    assert cotizacion_pdf.nombre_de_archivo("").endswith(".pdf")


# ----------------------------------------------------------------------
# 2. El PDF se suma a los documentos, no los sustituye
# ----------------------------------------------------------------------

def test_el_pdf_se_anexa_sin_borrar_lo_que_subio_una_persona():
    """`archivoUrl` es la lista de documentos de la línea (columna CARPETA).
    Sustituirla sería justo la pérdida de información que esto quiere evitar."""
    documentos = cotizacion_pdf.anexar_a_documentos(
        "https://drive/COTIZACION-CLIENTE\nhttps://drive/PLANO-1",
        "https://supabase/COTIZACION.pdf")

    assert documentos.split("\n") == [
        "https://drive/COTIZACION-CLIENTE",
        "https://drive/PLANO-1",
        "https://supabase/COTIZACION.pdf",
    ]


def test_guardar_dos_veces_no_repite_la_misma_url():
    documentos = cotizacion_pdf.anexar_a_documentos(
        "https://supabase/COTIZACION.pdf", "https://supabase/COTIZACION.pdf")

    assert documentos == "https://supabase/COTIZACION.pdf"


def test_una_orden_sin_adjuntos_estrena_la_lista_con_el_pdf():
    assert cotizacion_pdf.anexar_a_documentos("", "https://supabase/COTIZACION.pdf") == (
        "https://supabase/COTIZACION.pdf")


# ----------------------------------------------------------------------
# 3. El archivado: a dónde va y qué pasa si falla
# ----------------------------------------------------------------------

def test_el_pdf_se_archiva_bajo_el_cliente_y_con_su_tipo():
    subidas = {}

    def _subir(datos, tipo, nombre, cliente, fecha):
        subidas.update({"datos": datos, "tipo": tipo, "nombre": nombre,
                        "cliente": cliente, "fecha": fecha})
        return {"success": True, "fileUrl": "https://supabase/2026/SEPTIEMBRE/ACME/x.pdf"}

    with mock.patch("api.services.storage.subir", _subir):
        resultado = cotizacion_pdf.archivar(ORDEN, FOLIO)

    assert resultado["success"] is True
    assert resultado["fileUrl"] == "https://supabase/2026/SEPTIEMBRE/ACME/x.pdf"
    assert subidas["tipo"] == "application/pdf"
    assert subidas["cliente"] == "ACME INDUSTRIAL"
    assert subidas["nombre"] == f"COTIZACION {FOLIO}.pdf"
    # Llega en base64, que es lo que `storage.subir` decodifica.
    import base64
    assert base64.b64decode(subidas["datos"])[:5] == b"%PDF-"


def test_si_storage_no_esta_configurado_se_dice_y_no_se_lanza():
    with mock.patch("api.services.storage.subir",
                    lambda *a, **k: {"success": False,
                                     "message": "Supabase no está configurado: "
                                                "el archivo NO se subió."}):
        resultado = cotizacion_pdf.archivar(ORDEN, FOLIO)

    assert resultado["success"] is False
    assert resultado["fileUrl"] == ""
    assert "no se archivó" in resultado["message"]
    assert "Supabase no está configurado" in resultado["message"]


def test_un_fallo_al_emitir_el_pdf_se_reporta_en_vez_de_propagarse():
    """El llamador guarda la orden pase lo que pase: `archivar` no lanza."""
    with mock.patch.object(cotizacion_pdf, "construir_pdf",
                           side_effect=RuntimeError("fuente rota")):
        resultado = cotizacion_pdf.archivar(ORDEN, FOLIO)

    assert resultado["success"] is False
    assert "fuente rota" in resultado["message"]


# ----------------------------------------------------------------------
# 4. La línea del tracker: el PDF en la columna CARPETA
# ----------------------------------------------------------------------
#
# `archivoUrl` es lo que la fila guarda en `ARCHIVO`, alias de la columna
# `carpeta` (`backend/schemas/task.py`) — la del icono de nube que el dueño
# señaló en la captura. Las tareas derivadas del programa la heredan
# (`tareas_de_programa`), así que quien ejecuta el trabajo abre la cotización
# desde su propia línea.

def _motor():
    from backend.core.engines.memoria import MemoryEngine

    return MemoryEngine({
        "quotes": [], "tasks": [], "people": [], "plan_semanal": [],
        "task_involucrados": [], "system_log": [], "work_orders": [],
        "wo_materiales": [], "wo_mano_obra": [], "wo_herramientas": [],
        "wo_equipos": [], "wo_programa": [],
    })


def _guardar(orden, url_pdf="https://supabase/2026/SEPTIEMBRE/ACME/COTIZACION.pdf",
             exito=True, mensaje=""):
    """Guarda la orden con el archivado simulado y devuelve (resultado, tareas)."""
    from api.services import work_order

    tareas = []
    respuesta = ({"success": True, "fileUrl": url_pdf, "message": ""} if exito
                 else {"success": False, "fileUrl": "", "message": mensaje})

    def _espiar_tarea(task_data, item, item_id, active_user):
        tareas.append(dict(task_data))
        return []

    with mock.patch.object(work_order, "_engine", _motor), \
         mock.patch.object(work_order, "_hay_base", lambda: True), \
         mock.patch.object(work_order, "save_to_obsidian", lambda *a, **k: None), \
         mock.patch.object(work_order, "_distribuir_tarea", _espiar_tarea), \
         mock.patch.object(cotizacion_pdf, "archivar", lambda *a, **k: respuesta):
        resultado = work_order.process_and_save_work_order([dict(orden)], "PREWORK_ORDER")
    return resultado, tareas


def test_al_guardar_la_orden_su_pdf_queda_en_los_documentos_de_la_linea():
    resultado, (tarea,) = _guardar(ORDEN)

    assert resultado["success"] is True
    documentos = tarea["ARCHIVO"].split("\n")
    assert documentos[-1] == "https://supabase/2026/SEPTIEMBRE/ACME/COTIZACION.pdf"
    # Y sigue estando lo que subió la persona.
    assert "https://drive.google.com/file/d/COTIZACION-DEL-CLIENTE/view" in documentos


def test_la_tarea_de_cada_responsable_hereda_el_pdf():
    """`tareas_de_programa` copia `ARCHIVO` de la cabecera: quien ejecuta el
    trabajo abre la cotización desde su propia línea del tracker."""
    from api.services import work_order

    _resultado, (tarea,) = _guardar(ORDEN)
    cabecera = {"FOLIO": FOLIO, "AREA": "ELECTROMECANICA", "CLASIFICACION": "AA",
                "FECHA": "09/09/26", "ARCHIVO": tarea["ARCHIVO"]}

    ((_persona, fila),) = work_order.tareas_de_programa(
        [{"description": "Levantar muro", "seccion": "TRABAJO",
          "responsable": "CUADRILLA 1"}], cabecera)

    assert "COTIZACION.pdf" in fila["ARCHIVO"]


def test_si_el_pdf_no_se_archiva_la_orden_se_guarda_igual_y_se_avisa():
    """Perder la orden entera por no poder archivar su PDF sería peor que el
    problema que este cambio resuelve."""
    resultado, (tarea,) = _guardar(
        ORDEN, exito=False,
        mensaje="La cotización en PDF no se archivó: Supabase no está configurado.")

    assert resultado["success"] is True
    assert resultado["ids"], "la orden no llegó a guardarse"
    assert any("no se archivó" in aviso for aviso in resultado["warnings"])
    # Los documentos que ya tenía siguen intactos.
    assert tarea["ARCHIVO"] == ORDEN["archivoUrl"]


# ----------------------------------------------------------------------
# 5. El diagnóstico: comprobar el archivado contra el Storage real
# ----------------------------------------------------------------------
#
# Las tres formas de fallar del archivado viven en la configuración del
# despliegue y desde la pantalla se ven igual: un aviso al guardar. Aquí se
# simula el Storage —no se puede tener uno en la suite— y se comprueba que el
# diagnóstico las distinga, que borre lo que sube y que no filtre credenciales.

class _AlmacenFalso:
    """Lo justo de `sb_manager.client.storage.from_(bucket)` que se usa."""

    def __init__(self):
        self.borrados = []

    def remove(self, rutas):
        self.borrados.extend(rutas)


def _diagnostico_con(subida=None, lectura=None, almacen=None, configurado=True):
    """Corre `diagnostico_storage` con el Storage simulado."""
    from api.services import storage
    from api.services.supabase_manager import sb_manager

    almacen = almacen or _AlmacenFalso()
    subida = subida or {"success": True, "path": "2026/SEPTIEMBRE/DIAGNOSTICO/x.pdf",
                        "fileUrl": "https://supabase/public/archivos/x.pdf"}
    lectura = lectura or {"ok": True, "codigo": 200, "detalle": "El PDF se lee."}

    cliente = mock.Mock()
    cliente.storage.from_.return_value = almacen

    # `is_configured` y `client` son propiedades del gestor y `client` lanza
    # sin credenciales: se sustituyen en la clase, no en la instancia.
    with mock.patch.object(type(sb_manager), "is_configured",
                           property(lambda _self: configurado)), \
         mock.patch.object(type(sb_manager), "client",
                           property(lambda _self: cliente)), \
         mock.patch.object(storage, "subir", lambda *a, **k: subida), \
         mock.patch.object(cotizacion_pdf, "_leer_url", lambda _url: lectura):
        return cotizacion_pdf.diagnostico_storage(), almacen


def _paso(reporte, nombre):
    encontrados = [p for p in reporte["pasos"] if p["paso"] == nombre]
    assert encontrados, f"el diagnóstico no reportó el paso {nombre!r}"
    return encontrados[0]


def test_el_diagnostico_recorre_el_viaje_completo_cuando_todo_funciona():
    reporte, almacen = _diagnostico_con()

    assert reporte["ok"] is True
    assert [p["paso"] for p in reporte["pasos"]] == [
        "configuracion", "emision", "subida", "lectura", "borrado"]
    assert all(p["ok"] for p in reporte["pasos"])
    assert almacen.borrados == ["2026/SEPTIEMBRE/DIAGNOSTICO/x.pdf"], (
        "el archivo de prueba se quedó en el bucket")


def test_sin_credenciales_el_diagnostico_lo_dice_y_no_sube_nada():
    reporte, almacen = _diagnostico_con(configurado=False)

    assert reporte["ok"] is False
    assert _paso(reporte, "configuracion")["ok"] is False
    assert "SUPABASE_URL" in _paso(reporte, "configuracion")["detalle"]
    assert almacen.borrados == []


def test_si_el_bucket_rechaza_la_subida_el_diagnostico_para_ahi():
    reporte, _almacen = _diagnostico_con(
        subida={"success": False, "message": "Bucket not found"})

    assert reporte["ok"] is False
    assert _paso(reporte, "subida")["ok"] is False
    assert "Bucket not found" in _paso(reporte, "subida")["detalle"]
    assert not [p for p in reporte["pasos"] if p["paso"] == "lectura"]


def test_un_bucket_privado_se_distingue_de_uno_que_no_existe():
    """El fallo que más cuesta ver: la subida funciona y el enlace que se
    guarda en la columna CARPETA no abre. Ya pasó con `ticket-evidencia`."""
    reporte, almacen = _diagnostico_con(
        lectura={"ok": False, "codigo": 404,
                 "detalle": "La URL pública respondió 404."})

    assert reporte["ok"] is False
    assert _paso(reporte, "subida")["ok"] is True
    assert _paso(reporte, "lectura")["ok"] is False
    assert "público" in reporte["detalle"]
    # Y aun así limpia lo que subió.
    assert almacen.borrados


def test_el_diagnostico_no_devuelve_ninguna_credencial():
    import json as _json

    with mock.patch.dict(os.environ, {"SUPABASE_URL": "https://proyecto.supabase.co",
                                      "SUPABASE_KEY": "clave-secretisima"}):
        reporte, _almacen = _diagnostico_con()

    assert "clave-secretisima" not in _json.dumps(reporte)


def test_la_lectura_reconoce_un_cuerpo_que_no_es_pdf():
    """Storage contesta su error como JSON; el cuerpo dice cuál y cabe en el
    detalle. Sin esto, un 200 con un error dentro pasaría por bueno."""
    class _Respuesta:
        status = 200

        def read(self, _n=None):
            return b'{"statusCode":"404","error":"Bucket not found"}'

        def __enter__(self):
            return self

        def __exit__(self, *_a):
            return False

    with mock.patch("urllib.request.urlopen", lambda *a, **k: _Respuesta()):
        resultado = cotizacion_pdf._leer_url("https://supabase/public/archivos/x.pdf")

    assert resultado["ok"] is False
    assert "Bucket not found" in resultado["detalle"]


def test_la_lectura_acepta_un_pdf_de_verdad():
    class _Respuesta:
        status = 200

        def read(self, _n=None):
            return b"%PDF-1.7 lo que sea"

        def __enter__(self):
            return self

        def __exit__(self, *_a):
            return False

    with mock.patch("urllib.request.urlopen", lambda *a, **k: _Respuesta()):
        resultado = cotizacion_pdf._leer_url("https://supabase/public/archivos/x.pdf")

    assert resultado["ok"] is True


def test_el_endpoint_de_diagnostico_responde_el_reporte():
    from fastapi.testclient import TestClient

    import api.main as main

    with mock.patch.object(cotizacion_pdf, "diagnostico_storage",
                           lambda: {"ok": True, "bucket": "archivos",
                                    "pasos": [], "detalle": "Todo bien."}):
        respuesta = TestClient(main.app).get("/api/cotizacion/diagnostico")

    assert respuesta.status_code == 200
    assert respuesta.json()["ok"] is True
    assert respuesta.json()["bucket"] == "archivos"


def test_el_script_de_verificacion_sale_con_uno_cuando_el_archivado_falla():
    """`scripts/verificar_storage_cotizacion.py` es la vía sin desplegar: su
    código de salida es lo que mira quien lo corre en una terminal."""
    import importlib.util

    ruta = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                        "scripts", "verificar_storage_cotizacion.py")
    spec = importlib.util.spec_from_file_location("verificar_storage_cotizacion", ruta)
    modulo = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(modulo)

    with mock.patch.object(cotizacion_pdf, "diagnostico_storage",
                           lambda: {"ok": False, "bucket": "archivos", "detalle": "No.",
                                    "pasos": [{"paso": "subida", "ok": False,
                                               "detalle": "Bucket not found"}]}):
        assert modulo.main() == 1

    with mock.patch.object(cotizacion_pdf, "diagnostico_storage",
                           lambda: {"ok": True, "bucket": "archivos", "detalle": "Si.",
                                    "pasos": []}):
        assert modulo.main() == 0
