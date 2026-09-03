"""
Cerrar una tarea y subir su evidencia, recorrido por el navegador.

`tests/test_cierre_con_evidencia.py` comprueba la regla y el backend. Lo que
esas pruebas no pueden ver es lo único que la persona ve: qué dice la pantalla
al intentar cerrar, y si el archivo grande llega o se queda girando.

Los dos reportes que originan estas pruebas:

    BUG-0009 · CARLOS_MENDEZ — «no me deja cerrar tareas que capture ni cargar
    archivos "pesados"»
    BUG-0010 · ROCIO_CASTRO — «me marca q no subo archivo al correo para cerrar
    una tarea»

Se cubren los tres momentos del recorrido:

1. cerrar al 100% con la evidencia en `CARPETA` y sin nada en `CORREO` — el
   caso exacto del reporte, que antes salía rechazado;
2. cerrar sin ninguna evidencia — sigue bloqueado, pero el aviso ahora dice
   qué hacer;
3. subir un archivo de 20 MB — antes moría en el cuerpo de 4.5 MB de la
   función y el spinner se quedaba girando; ahora va directo a Storage, y si
   algo falla se ve en pantalla.
"""

from __future__ import annotations

import json

from playwright.sync_api import sync_playwright

BASE_URL = "http://localhost:8000"

ENCABEZADOS = ["FOLIO", "CONCEPTO", "RESPONSABLE", "AVANCE", "ESTATUS",
               "ARCHIVO", "CORREO", "CARPETA"]

FILA_CON_CARPETA = {
    "FOLIO": "CM-0001", "CONCEPTO": "REVISAR PLANOS DE NAVE",
    "RESPONSABLE": "CARLOS MENDEZ", "AVANCE": "100", "ESTATUS": "HECHO",
    "ARCHIVO": "", "CORREO": "", "CARPETA": "https://storage.local/evidencia.pdf",
}

FILA_SIN_EVIDENCIA = {
    "FOLIO": "CM-0002", "CONCEPTO": "ACTUALIZAR ISOMETRICOS",
    "RESPONSABLE": "CARLOS MENDEZ", "AVANCE": "100", "ESTATUS": "HECHO",
    "ARCHIVO": "", "CORREO": "", "CARPETA": "",
}

MONTAR_TRACKER = """(datos) => {
    const app = document.querySelector('#app').__vue_app__._instance.proxy;
    app.isLoggedIn = true;
    app.currentUsername = 'CARLOS_MENDEZ';
    app.currentUser = 'CARLOS MENDEZ';
    app.currentView = 'STAFF_TRACKER';
    app.trackerSubView = 'TASKS';
    app.staffTracker.name = 'CARLOS MENDEZ';
    app.staffTracker.isLoading = false;
    app.staffTracker.headers = datos.encabezados;
    app.staffTracker.data = datos.filas;
    app.staffTracker.history = [];
}"""

# Se guarda la fila que la vista ya tiene montada (la misma referencia que el
# botón de la tabla le pasaría a `saveRow`), no una copia.
GUARDAR_FILA = """(folio) => {
    const app = document.querySelector('#app').__vue_app__._instance.proxy;
    const fila = app.staffTracker.data.find(f => f.FOLIO === folio);
    app.saveRow(fila);
}"""

TEXTO_DEL_AVISO = """() => {
    const modal = document.querySelector('.swal2-popup');
    if (!modal) return null;
    return {
        titulo: (modal.querySelector('.swal2-title') || {}).textContent || '',
        texto: (modal.querySelector('#swal2-html-container') || {}).textContent || ''
    };
}"""


def _tracker_montado(page, filas):
    page.goto(BASE_URL)
    page.wait_for_selector("#app", state="attached", timeout=15000)
    page.wait_for_function(
        "() => document.querySelector('#app') && document.querySelector('#app').__vue_app__",
        timeout=15000)
    page.evaluate(MONTAR_TRACKER, {"encabezados": ENCABEZADOS, "filas": filas})
    page.wait_for_selector(".table-excel tbody tr", timeout=10000)


def _responder(route, cuerpo: dict, estado: int = 200) -> None:
    route.fulfill(status=estado, body=json.dumps(cuerpo),
                  headers={"content-type": "application/json"})


# ---------------------------------------------------------------------------
# 1. Cerrar con una sola evidencia
# ---------------------------------------------------------------------------

def test_se_cierra_con_la_evidencia_en_carpeta_aunque_correo_este_vacio():
    """
    El reporte de ROCIO_CASTRO: la evidencia está cargada, pero en otra
    columna. Antes la pantalla contestaba «Falta subir archivos a CORREO» y no
    dejaba cerrar; ahora guarda.
    """
    with sync_playwright() as p:
        navegador = p.chromium.launch(headless=True)
        page = navegador.new_page(viewport={"width": 1400, "height": 800})
        try:
            guardados = []

            def guardar(route):
                guardados.append(route.request.post_data)
                _responder(route, {"success": True, "data": dict(FILA_CON_CARPETA)})

            page.route("**/api/legacy/updateTask", guardar)
            page.route("**/api/legacy/saveTrackerBatch", guardar)

            _tracker_montado(page, [dict(FILA_CON_CARPETA)])
            page.evaluate(GUARDAR_FILA, "CM-0001")
            page.wait_for_selector(".swal2-popup", timeout=10000)

            aviso = page.evaluate(TEXTO_DEL_AVISO)
            assert "evidencia" not in (aviso["titulo"] + aviso["texto"]).lower(), aviso
            assert guardados, "la fila ni siquiera se mandó a guardar"
        finally:
            navegador.close()


def test_sin_ninguna_evidencia_el_aviso_dice_que_basta_una():
    """Cerrar sin evidencia sigue bloqueado (Política §3.4), pero con instrucciones."""
    with sync_playwright() as p:
        navegador = p.chromium.launch(headless=True)
        page = navegador.new_page(viewport={"width": 1400, "height": 800})
        try:
            intentos = []
            page.route("**/api/legacy/updateTask",
                       lambda route: (intentos.append(1), _responder(route, {"success": True})))

            _tracker_montado(page, [dict(FILA_SIN_EVIDENCIA)])
            page.evaluate(GUARDAR_FILA, "CM-0002")
            page.wait_for_selector(".swal2-popup", timeout=10000)

            aviso = page.evaluate(TEXTO_DEL_AVISO)
            assert aviso["titulo"] == "Falta la evidencia", aviso
            # El aviso nombra las tres columnas: la persona elige dónde subirla.
            for columna in ("ARCHIVO", "CORREO", "CARPETA"):
                assert columna in aviso["texto"], aviso
            assert intentos == [], "una fila sin evidencia no debe llegar al backend"
        finally:
            navegador.close()


# ---------------------------------------------------------------------------
# 2. El archivo pesado
# ---------------------------------------------------------------------------

# El archivo se fabrica DENTRO de la página: mandar 20 MB por el puente de
# Playwright, byte a byte en JSON, tarda minutos y no prueba nada más.
SUBIR_ARCHIVO = """async (tamano) => {
    const archivo = new File([new Uint8Array(tamano)], 'evidencia.pdf', { type: 'application/pdf' });
    return await window.subirArchivoAlmacen(archivo);
}"""


def test_un_archivo_de_20_mb_va_directo_a_storage_y_no_por_la_funcion():
    """
    El corazón de BUG-0009. Por `/api/legacy/upload` este archivo nunca habría
    pasado: en base64 son ~27 MB de cuerpo y la plataforma corta en 4.5 MB.
    Aquí se comprueba que los bytes salen por la URL firmada y que la ruta
    vieja no se toca.
    """
    with sync_playwright() as p:
        navegador = p.chromium.launch(headless=True)
        page = navegador.new_page(viewport={"width": 1400, "height": 800})
        try:
            recibidos = {"firmas": 0, "put": 0, "bytes": 0, "json": 0}

            def firmar(route):
                recibidos["firmas"] += 1
                _responder(route, {
                    "success": True,
                    "uploadUrl": "https://supabase.local/storage/v1/object/upload/sign/archivos/2026/AGOSTO/evidencia.pdf?token=T",
                    "fileUrl": "https://supabase.local/storage/v1/object/public/archivos/2026/AGOSTO/evidencia.pdf",
                    "path": "2026/AGOSTO/evidencia.pdf",
                    "maxBytes": 35 * 1024 * 1024,
                })

            def recibir_put(route):
                recibidos["put"] += 1
                recibidos["bytes"] = len(route.request.post_data_buffer or b"")
                _responder(route, {"Key": "archivos/2026/AGOSTO/evidencia.pdf"})

            def ruta_vieja(route):
                recibidos["json"] += 1
                _responder(route, {"success": False, "message": "no debería usarse"})

            page.route("**/api/legacy/uploadUrl", firmar)
            page.route("**/api/legacy/upload", ruta_vieja)
            page.route("https://supabase.local/**", recibir_put)

            _tracker_montado(page, [dict(FILA_SIN_EVIDENCIA)])
            resultado = page.evaluate(SUBIR_ARCHIVO, 20 * 1024 * 1024)

            assert resultado["success"] is True, resultado
            assert resultado["fileUrl"].endswith("evidencia.pdf"), resultado
            assert recibidos["firmas"] == 1
            assert recibidos["put"] == 1
            assert recibidos["bytes"] == 20 * 1024 * 1024, recibidos
            assert recibidos["json"] == 0, "el archivo volvió a pasar por el cuerpo de la función"
        finally:
            navegador.close()


def test_si_la_subida_falla_la_pantalla_lo_dice_y_no_se_queda_girando():
    """
    El otro medio defecto: sin `withFailureHandler` el fallo solo salía por
    consola. Se comprueba en la celda del tracker, que es donde el spinner
    quedaba abierto.
    """
    with sync_playwright() as p:
        navegador = p.chromium.launch(headless=True)
        page = navegador.new_page(viewport={"width": 1400, "height": 800})
        try:
            page.route("**/api/legacy/uploadUrl", lambda route: _responder(
                route, {"success": False, "message": "Supabase no está configurado."}))

            _tracker_montado(page, [dict(FILA_SIN_EVIDENCIA)])

            # Se recorre la puerta real de la celda: `openCellUpload` abre el
            # selector de archivo y su `change` dispara `handleCellFile`.
            with page.expect_file_chooser() as selector:
                page.evaluate("""() => {
                    const app = document.querySelector('#app').__vue_app__._instance.proxy;
                    app.openCellUpload(app.staffTracker.data[0], 'ARCHIVO');
                }""")
            selector.value.set_files({"name": "evidencia.pdf",
                                      "mimeType": "application/pdf",
                                      "buffer": b"%PDF-1.4 evidencia"})

            page.wait_for_selector(".swal2-popup .swal2-title", timeout=10000)
            aviso = page.evaluate(TEXTO_DEL_AVISO)

            assert aviso["titulo"] == "No se subió el archivo", aviso
            assert "Supabase" in aviso["texto"], aviso
            # Y el spinner cerró: el diálogo que quedó es el del error, con su
            # botón utilizable.
            assert page.locator(".swal2-loader").is_visible() is False
        finally:
            navegador.close()


# ---------------------------------------------------------------------------
# 3. «Guardar Todo» con varias filas a las que les falta la evidencia
# ---------------------------------------------------------------------------
# BUG-0023 (ALFONSO_CORREA): «las celdas del 1,3,4,5,6,7 son actividades ya
# realizadas y las puse al cien % y siguen igual».
#
# Medido contra la base: sus ocho filas activas no tienen archivo ni en CORREO
# ni en CARPETA, así que la puerta de §3.4 las rechaza —correctamente— y el
# 100 % nunca sale del navegador. Lo que estaba mal no es la regla sino cómo se
# cuenta: `saveAllTrackerRows` cortaba en la PRIMERA fila sin evidencia,
# nombraba solo esa y no guardaba nada. Con seis filas cerradas de golpe, la
# persona subía un archivo, volvía a guardar, y le salía la siguiente: seis
# vueltas para enterarse de las seis, sin que nada se guardara por el camino.
#
# La regla no se toca: sigue sin guardarse nada mientras falte una evidencia.
# Lo que cambia es que el aviso las nombra TODAS de una vez.

FILA_SIN_EVIDENCIA_2 = {
    "FOLIO": "CM-0003", "CONCEPTO": "ENTREGAR REPORTE FOTOGRAFICO",
    "RESPONSABLE": "CARLOS MENDEZ", "AVANCE": "100", "ESTATUS": "HECHO",
    "ARCHIVO": "", "CORREO": "", "CARPETA": "",
}

GUARDAR_TODO = """() => {
    document.querySelector('#app').__vue_app__._instance.proxy.saveAllTrackerRows();
}"""


def test_guardar_todo_nombra_todas_las_filas_a_las_que_les_falta_evidencia():
    """El aviso tiene que listar las dos, no solo la primera."""
    with sync_playwright() as p:
        navegador = p.chromium.launch(headless=True)
        page = navegador.new_page(viewport={"width": 1400, "height": 800})
        try:
            intentos = []
            page.route("**/api/legacy/saveTrackerBatch",
                       lambda route: (intentos.append(1), _responder(route, {"success": True})))

            _tracker_montado(page, [dict(FILA_SIN_EVIDENCIA),
                                    dict(FILA_CON_CARPETA),
                                    dict(FILA_SIN_EVIDENCIA_2)])
            page.evaluate(GUARDAR_TODO)
            page.wait_for_selector(".swal2-popup", timeout=10000)

            aviso = page.evaluate(TEXTO_DEL_AVISO)
            assert "CM-0002" in aviso["texto"], aviso
            assert "CM-0003" in aviso["texto"], aviso
            assert "CM-0001" not in aviso["texto"], "esa sí trae evidencia"
            assert intentos == [], "no se guarda nada mientras falte una evidencia"
        finally:
            navegador.close()


def test_guardar_todo_dice_en_que_columnas_se_sube_la_evidencia():
    """Nombrar la fila no basta: hay que decir dónde se sube el archivo."""
    with sync_playwright() as p:
        navegador = p.chromium.launch(headless=True)
        page = navegador.new_page(viewport={"width": 1400, "height": 800})
        try:
            _tracker_montado(page, [dict(FILA_SIN_EVIDENCIA)])
            page.evaluate(GUARDAR_TODO)
            page.wait_for_selector(".swal2-popup", timeout=10000)

            aviso = page.evaluate(TEXTO_DEL_AVISO)
            for columna in ("ARCHIVO", "CORREO", "CARPETA"):
                assert columna in aviso["texto"], aviso
        finally:
            navegador.close()


def test_guardar_todo_no_se_traba_con_las_filas_que_si_traen_evidencia():
    """Con la evidencia puesta, «Guardar Todo» llega a su confirmación."""
    with sync_playwright() as p:
        navegador = p.chromium.launch(headless=True)
        page = navegador.new_page(viewport={"width": 1400, "height": 800})
        try:
            _tracker_montado(page, [dict(FILA_CON_CARPETA)])
            page.evaluate(GUARDAR_TODO)
            page.wait_for_selector(".swal2-popup", timeout=10000)

            aviso = page.evaluate(TEXTO_DEL_AVISO)
            assert "evidencia" not in (aviso["titulo"] + aviso["texto"]).lower(), aviso
            assert "Guardar Todo" in aviso["titulo"] or "guard" in aviso["titulo"].lower(), aviso
        finally:
            navegador.close()
