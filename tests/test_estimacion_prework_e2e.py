"""De la agencia a la cotización: el recorrido completo, sin partirlo en dos.

Lo que faltaba probar. `tests/test_paperclip_estimaciones.py` verifica el
formulario con una respuesta escrita a mano, y `tests/test_estimacion_agencia.py`
verifica el backend sin navegador. Entre las dos quedaba el hueco por el que se
coló esta regresión dos veces: **nadie comprobaba que la respuesta que produce
la agencia de verdad llene las tablas del formulario de verdad**.

Aquí el JSON no se escribe a mano: sale de correr el grafo completo de
`api/paperclip_agents.py` (con el modelo simulado, que es lo único que no se
puede tener en una prueba) y se le entrega tal cual al `index.html` que usa el
usuario. Se pulsa el botón real de la Agencia Paperclip y se comprueban las
tres tablas que el dueño nombró —MATERIALES, HERRAMIENTAS y MANO DE OBRA—, lo
que se ve en pantalla y los totales con los que sale la cotización.

Incluye la corrida en la que el Integrador se cae: es el modo de fallo que
dejaba las tablas vacías y el que el dueño reportó.
"""

from __future__ import annotations

import json
from unittest import mock

import pytest
from playwright.sync_api import sync_playwright

from api.paperclip_agents import StructuredAgencyData
from tests.test_estimacion_agencia import correr_agencia_simulada

BASE_URL = "http://localhost:8000"

DISENO = "Muro de block de 10 x 3 m de altura en nave industrial"

# Totales esperados, calculados a mano desde los datos de `test_estimacion_agencia`:
#   Materiales : 450 x 18.50 + 12 x 220        = 8,325.00 + 2,640.00 = 10,965.00
#   Herramienta: 1 x 850                       =    850.00
#   Mano de obra: 2,800 x 3 personas x 2 sem   = 16,800.00
#   Equipo     : 24 x 1 día x 120              =  2,880.00
MATERIALES_ESPERADO = 10_965.00
HERRAMIENTAS_ESPERADO = 850.00
MANO_DE_OBRA_ESPERADO = 16_800.00
EQUIPO_ESPERADO = 2_880.00
SUBTOTAL_ESPERADO = (MATERIALES_ESPERADO + HERRAMIENTAS_ESPERADO
                     + MANO_DE_OBRA_ESPERADO + EQUIPO_ESPERADO)


def _respuesta_de_la_agencia(fallas=()) -> dict:
    """La respuesta del endpoint, producida por `run_paperclip_agency` de verdad.

    No se escribe a mano ni una clave: se corre la agencia entera con el LLM
    simulado y se le entrega al navegador lo que devolvería el endpoint. Es lo
    que faltaba —cada mitad estaba probada contra su propia idea de la otra— y
    por ese hueco la regresión pasó dos veces.
    """
    return correr_agencia_simulada(fallas=fallas)


@pytest.fixture
def pagina():
    with sync_playwright() as p:
        navegador = p.chromium.launch(headless=True)
        page = navegador.new_page(viewport={"width": 1500, "height": 950})
        try:
            page.goto(BASE_URL)
            page.wait_for_selector(".login-card", state="visible", timeout=20000)
            page.evaluate(
                "() => { const app = document.querySelector('#app').__vue_app__"
                "._instance.proxy;"
                " app.isLoggedIn = true; app.currentView = 'WORKORDER_FORM'; }")
            page.wait_for_selector("#campoConcepto", timeout=20000)
            yield page
        finally:
            navegador.close()


def _app(page):
    return "document.querySelector('#app').__vue_app__._instance.proxy"


def _correr_agencia(page, respuesta):
    """Pulsa el botón real de la Agencia Paperclip con esa respuesta del backend."""
    page.evaluate(
        "(r) => { window.__peticiones = 0;"
        " ApiService.runPaperclipAgents = async () => { window.__peticiones++; return r; }; }",
        respuesta)
    page.fill("#campoConcepto", DISENO)
    page.click("button[title^='Ejecutar Agencia Paperclip']")
    page.wait_for_function(f"() => {_app(page)}.isPaperclipRunning === false",
                           timeout=20000)
    assert page.evaluate("() => window.__peticiones") == 1, (
        "el botón de la Agencia Paperclip no llamó al backend")


def _tabla(page, nombre):
    return page.evaluate(
        f"() => JSON.parse(JSON.stringify({_app(page)}.{nombre}.items))")


def _fila(page, tabla, campo, valor, **otros):
    """La fila de la estimación en esa tabla.

    `otros` desempata cuando el formulario ya traía una fila parecida: MANO DE
    OBRA arranca con un renglón de ejemplo ("Albañil", $1,200 la semana) que se
    llama igual que el puesto estimado, y sin distinguirlos esta prueba miraría
    la fila de ejemplo y daría por buena una estimación que nunca entró.
    """
    filas = [f for f in _tabla(page, tabla)
             if f.get(campo) == valor
             and all(str(f.get(k)) == str(v) for k, v in otros.items())]
    assert filas, f"{tabla}: no llegó la fila {valor!r} de la estimación"
    assert len(filas) == 1, f"{tabla}: la fila {valor!r} se insertó {len(filas)} veces"
    return filas[0]


# ----------------------------------------------------------------------
# 1. Las tres tablas que el dueño nombró
# ----------------------------------------------------------------------

def test_materiales_herramientas_y_mano_de_obra_quedan_escritos(pagina):
    _correr_agencia(pagina, _respuesta_de_la_agencia())

    block = _fila(pagina, "requiredMaterials", "description", "Block hueco 15x20x40")
    assert str(block["quantity"]) == "450"
    assert str(block["cost"]) == "18.5"
    assert float(block["total"]) == pytest.approx(8325.0)

    cemento = _fila(pagina, "requiredMaterials", "description", "Cemento gris")
    assert float(cemento["total"]) == pytest.approx(2640.0)

    revolvedora = _fila(pagina, "toolsRequired", "description", "Revolvedora de 1 saco")
    assert float(revolvedora["total"]) == pytest.approx(850.0)

    albanil = _fila(pagina, "laborTable", "category", "Albañil", salary="2800")
    assert str(albanil["personnel"]) == "3"
    assert str(albanil["weeks"]) == "2"
    assert str(albanil["salary"]) == "2800"
    assert float(albanil["total"]) == pytest.approx(16800.0)

    andamio = _fila(pagina, "specialEquipment", "description", "Andamio tubular")
    assert float(andamio["total"]) == pytest.approx(2880.0)


def test_la_estimacion_se_ve_en_la_pantalla(pagina):
    """Que la fila exista en el arreglo no basta: el usuario la tiene que ver."""
    _correr_agencia(pagina, _respuesta_de_la_agencia())

    valores = pagina.evaluate(
        "() => Array.from(document.querySelectorAll('input')).map(i => i.value)")
    for esperado in ("Block hueco 15x20x40", "Cemento gris",
                     "Revolvedora de 1 saco", "Albañil", "Andamio tubular"):
        assert esperado in valores, f"'{esperado}' no se ve en el formulario"


# ----------------------------------------------------------------------
# 2. Los datos sirven para sacar la cotización
# ----------------------------------------------------------------------

def test_los_totales_de_la_cotizacion_incluyen_la_estimacion(pagina):
    """Lo que pidió el dueño: que los datos sirvan «para sacar la cotización».

    Se comprueban los cuatro totales por tabla y el subtotal del tablero, que
    es el número con el que se cotiza. La fila de ejemplo con la que arranca
    MANO DE OBRA (Albañil $1,200) sigue ahí: por eso se compara contra el
    total previo más lo estimado, y no contra lo estimado a secas.
    """
    previo = pagina.evaluate(f"() => {_app(pagina)}.dashboardSubtotal")
    labor_previo = pagina.evaluate(f"() => {_app(pagina)}.laborTableTotal")

    _correr_agencia(pagina, _respuesta_de_la_agencia())

    totales = pagina.evaluate(
        f"() => ({{ materiales: {_app(pagina)}.materialsTotal,"
        f" herramientas: {_app(pagina)}.toolsTotal,"
        f" manoObra: {_app(pagina)}.laborTableTotal,"
        f" equipo: {_app(pagina)}.specialEquipTotal,"
        f" subtotal: {_app(pagina)}.dashboardSubtotal,"
        f" total: {_app(pagina)}.dashboardTotal }})")

    assert totales["materiales"] == pytest.approx(MATERIALES_ESPERADO)
    assert totales["herramientas"] == pytest.approx(HERRAMIENTAS_ESPERADO)
    assert totales["manoObra"] == pytest.approx(labor_previo + MANO_DE_OBRA_ESPERADO)
    assert totales["equipo"] == pytest.approx(EQUIPO_ESPERADO)
    assert totales["subtotal"] == pytest.approx(previo + SUBTOTAL_ESPERADO)
    # El gran total del tablero agrega 15% de utilidad sobre el subtotal.
    assert totales["total"] == pytest.approx(totales["subtotal"] * 1.15)


def test_el_analisis_de_ingenieria_se_escribe_en_la_descripcion(pagina):
    """El informe también se perdía: el formulario leía `result.estructuracion`,
    una clave que el backend no manda en ninguna respuesta."""
    _correr_agencia(pagina, _respuesta_de_la_agencia())

    descripcion = pagina.evaluate(f"() => {_app(pagina)}.workorderData.conceptoDesc")
    assert "--- Análisis de Ingeniería ---" in descripcion
    assert "Catálogo de Conceptos" in descripcion
    assert "TOTAL ESTIMADO DEL PROYECTO" in descripcion


# ----------------------------------------------------------------------
# 3. La corrida que el dueño reportó: el Integrador se cae
# ----------------------------------------------------------------------

def test_las_tablas_se_llenan_aunque_el_integrador_se_caiga(pagina):
    """El fallo reportado, de punta a punta: la última llamada al modelo
    revienta y la estimación llega igual porque sale del presupuesto."""
    respuesta = _respuesta_de_la_agencia(fallas=(StructuredAgencyData,))
    assert respuesta["estimacion_origen"] == "estructura"

    _correr_agencia(pagina, respuesta)

    assert _fila(pagina, "requiredMaterials", "description", "Block hueco 15x20x40")
    assert _fila(pagina, "toolsRequired", "description", "Revolvedora de 1 saco")
    assert _fila(pagina, "laborTable", "category", "Albañil", salary="2800")


def test_una_estimacion_que_no_se_pudo_armar_lo_dice(pagina):
    """Cero filas tiene dos causas y el usuario necesita distinguirlas. Este es
    el caso "la agencia no pudo", que antes se anunciaba igual que "no había
    nada que estimar"."""
    vacia = StructuredAgencyData(laborTable=[], requiredMaterials=[], toolsRequired=[],
                                 specialEquipment=[], viaticosTable=[])
    respuesta = dict(_respuesta_de_la_agencia(),
                     structured_data=json.dumps(vacia.model_dump()),
                     estimacion_origen="vacia")
    pagina.evaluate(
        "() => { window.__avisos = [];"
        " Swal.fire = (o) => { window.__avisos.push(o);"
        "   return Promise.resolve({ isConfirmed: true }); }; }")

    _correr_agencia(pagina, respuesta)

    (aviso,) = pagina.evaluate("() => window.__avisos")
    assert aviso["icon"] == "warning"
    assert "no pudo armar la estimación" in aviso["text"]


# ----------------------------------------------------------------------
# 4. La clave con la que corre la agencia
# ----------------------------------------------------------------------
# «Paperclip usa apikeys de Google, no de Groq» (el dueño, 2026-09-09). En
# Vercel cada invocación es un proceso nuevo, así que una clave guardada desde
# la pantalla vive en `localStorage` y solo llega al servidor si el formulario
# la manda — como ya hacía el agente de métricas y no hacía este.

def test_el_formulario_manda_la_clave_de_google_guardada(pagina):
    pagina.evaluate(
        "() => { localStorage.setItem('holtmont.geminiApiKey', 'AIzaDelNavegador');"
        " window.__enviado = null;"
        " ApiService.runPaperclipAgents = async (texto, clave) => {"
        "   window.__enviado = { texto, clave };"
        "   return { success: true, structured_data: '{}' }; }; }")
    pagina.fill("#campoConcepto", DISENO)
    pagina.click("button[title^='Ejecutar Agencia Paperclip']")
    pagina.wait_for_function(f"() => {_app(pagina)}.isPaperclipRunning === false",
                             timeout=20000)

    enviado = pagina.evaluate("() => window.__enviado")
    assert enviado["texto"] == DISENO
    assert enviado["clave"] == "AIzaDelNavegador", (
        "la agencia se quedó sin la clave de Google guardada en esta máquina")


def test_sin_clave_guardada_el_formulario_no_se_bloquea(pagina):
    """El despliegue con `GEMINI_API_KEY` en el entorno no necesita mandar nada:
    el servidor resuelve la clave solo."""
    pagina.evaluate("() => localStorage.removeItem('holtmont.geminiApiKey')")

    _correr_agencia(pagina, _respuesta_de_la_agencia())

    assert _fila(pagina, "requiredMaterials", "description", "Block hueco 15x20x40")


# ----------------------------------------------------------------------
# 5. De la estimación a la base: el recorrido que cierra la cotización
# ----------------------------------------------------------------------
#
# «Verifica que efectivamente coloque los datos para sacar la cotización».
# Las tablas llenas en pantalla no son el final: al guardar, cada bloque va a
# su tabla (`wo_materiales`, `wo_mano_obra`, `wo_herramientas`, `wo_equipos`).
# Esta prueba recorre las tres etapas sin inventarse ninguna:
#
#   agencia real -> formulario real -> lo que el formulario manda a guardar
#                -> `process_and_save_work_order` contra `MemoryEngine`.

def _payload_al_guardar(page):
    """Lo que `saveWorkOrder` manda a `apiSavePPCData`, sin llegar a la red.

    El reemplazo va en el prototipo y no en `google.script.run`:
    `withSuccessHandler` devuelve un adaptador NUEVO
    (`api_service.js`, `new GoogleScriptRunAdapter()`), así que un parche sobre
    la instancia se pierde en la cadena.
    """
    page.evaluate(
        "() => { window.__guardado = null;"
        " Object.getPrototypeOf(google.script.run).apiSavePPCData ="
        "   function (payload, usuario) {"
        "     window.__guardado = { payload, usuario };"
        "     this._successHandler({ success: true,"
        "                            ids: ['1001AC Electro 060826'] }); }; }")
    page.evaluate(f"() => {_app(page)}.saveWorkOrder()")
    page.wait_for_function(f"() => {_app(page)}.isSubmitting === false", timeout=20000)
    return page.evaluate("() => window.__guardado")


def _llenar_cabecera(page):
    page.evaluate(
        f"() => {{ const wo = {_app(page)}.workorderData;"
        " wo.cliente = 'ACME'; wo.especialidad = 'ELECTROMECANICA';"
        " wo.departamento = 'ELECTROMECANICA'; wo.clasificacion = 'AA';"
        " wo.requisitor = 'TERESA GARZA'; wo.cotizador = ['LUIS PEREYRA'];"
        " wo.tipoTrabajo = 'MANTENIMIENTO'; }")


def test_la_estimacion_viaja_en_lo_que_el_formulario_manda_a_guardar(pagina):
    _correr_agencia(pagina, _respuesta_de_la_agencia())
    _llenar_cabecera(pagina)

    guardado = _payload_al_guardar(pagina)
    assert guardado is not None, "el formulario no llegó a guardar"
    (orden,) = guardado["payload"]

    descripciones = [m["description"] for m in orden["materiales"]]
    assert "Block hueco 15x20x40" in descripciones
    assert "Cemento gris" in descripciones
    assert "Revolvedora de 1 saco" in [t["description"] for t in orden["herramientas"]]
    assert "Albañil" in [fila["category"] for fila in orden["manoObra"]]
    assert "Andamio tubular" in [e["description"] for e in orden["equipos"]]


def test_la_estimacion_llega_a_su_tabla_en_la_base(pagina):
    """El último tramo: cada bloque en su tabla, con folio y totales."""
    from api.services import work_order
    from backend.core.engines.memoria import MemoryEngine

    _correr_agencia(pagina, _respuesta_de_la_agencia())
    _llenar_cabecera(pagina)
    (orden,) = _payload_al_guardar(pagina)["payload"]

    motor = MemoryEngine({
        "quotes": [], "tasks": [], "people": [], "plan_semanal": [],
        "task_involucrados": [], "system_log": [], "work_orders": [],
        "wo_materiales": [], "wo_mano_obra": [], "wo_herramientas": [],
        "wo_equipos": [], "wo_programa": [],
    })
    with mock.patch.object(work_order, "_engine", lambda: motor), \
         mock.patch.object(work_order, "_hay_base", lambda: True), \
         mock.patch.object(work_order, "save_to_obsidian", lambda *a, **k: None), \
         mock.patch.object(work_order, "_distribuir_tarea", lambda *a, **k: []):
        resultado = work_order.process_and_save_work_order([orden], "PREWORK_ORDER")

    assert resultado.get("success") is not False, resultado
    (folio,) = resultado["ids"]

    # `.get`: la fila de ejemplo del formulario va vacía y el motor no escribe
    # las columnas sin valor.
    materiales = motor.select("wo_materiales")
    block = [m for m in materiales if m.get("descripcion") == "Block hueco 15x20x40"]
    assert block, "MATERIALES REQUERIDOS no llegó a `wo_materiales`"
    assert block[0]["folio"] == folio
    assert float(block[0]["total"]) == pytest.approx(8325.0)

    herramientas = motor.select("wo_herramientas")
    assert [t for t in herramientas
            if t.get("descripcion") == "Revolvedora de 1 saco"], (
        "HERRAMIENTAS REQUERIDAS no llegó a `wo_herramientas`")

    mano_obra = motor.select("wo_mano_obra")
    albanil = [fila for fila in mano_obra
               if fila.get("categoria") == "Albañil" and float(fila["salario"]) == 2800.0]
    assert albanil, "MANO DE OBRA no llegó a `wo_mano_obra`"
    assert float(albanil[0]["total"]) == pytest.approx(16800.0)

    equipos = motor.select("wo_equipos")
    assert [e for e in equipos if e.get("descripcion") == "Andamio tubular"], (
        "EQUIPO ESPECIAL no llegó a `wo_equipos`")
