"""
La Agencia Paperclip vuelve a llenar las tablas de la Pre Work Order.

Reporte del dueño (2026-09-08):

    «Quiero que el agente haga una estimación de MATERIALES REQUERIDOS,
    HERRAMIENTAS REQUERIDAS y MANO DE OBRA y los coloque dependiendo del diseño
    que le soliciten en paperclip. Ya lo hacía, no entiendo por qué ya no lo
    hace.»

La causa está medida y es una sola: **el formulario lee claves que el agente no
manda**. `StructuredAgencyData` (api/paperclip_agents.py) devuelve el JSON con
las mismas claves y los mismos campos que las tablas del formulario —
`requiredMaterials`, `toolsRequired`, `laborTable`, `specialEquipment`, con
`description` / `quantity` / `unit` / `cost` y `category` / `personnel` /
`weeks` / `salary`—, pero `runPaperclipAgents` de `index.html` buscaba
`parsedData.materiales`, `.herramientas`, `.mano_de_obra` y `.equipos`, con los
campos `m.material`, `t.herramienta`, `m.categoria`, `m.tiempo`, `e.equipo`.

Ninguna de esas claves existe en la respuesta, así que los cuatro `if` daban
`undefined`, no se insertaba una sola fila y el usuario veía el aviso verde
«Análisis completado» sobre las mismas tablas vacías de siempre. El fallo es
mudo por construcción: no hay excepción, no hay consola en rojo, solo tablas
que no cambian.

En la variante de actividad (`runActivityPaperclipAgents`) había un segundo
desajuste encima del primero: las filas se marcaban con `contextId`, y las
tablas del modal de recursos filtran por `activityId`
(`index.html`, `laborTable.items.filter(x => x.activityId === ...)`), de modo
que aunque las claves hubieran coincidido las filas habrían quedado invisibles.

Estas pruebas fijan el contrato en los dos sentidos: lo que el agente emite y
lo que el formulario inserta, recorrido en el navegador como lo recorre una
persona.
"""

from __future__ import annotations

import json

import pytest
from playwright.sync_api import sync_playwright

from api.paperclip_agents import (
    EquipmentItem,
    LaborItem,
    MaterialItem,
    StructuredAgencyData,
    ToolItem,
)

BASE_URL = "http://localhost:8000"

DISENO = "Muro de block de 10 x 3 m de altura en nave industrial"

# La estimación tal como sale de la agencia: se construye con los propios
# modelos del agente para que la prueba no pueda quedarse con una forma vieja
# del JSON. Si alguien renombra un campo en `StructuredAgencyData`, esto deja
# de compilar aquí antes que de fallar en producción.
ESTIMACION = StructuredAgencyData(
    laborTable=[
        LaborItem(category="ALBAÑIL", personnel="3", unit="semana",
                  weeks="2", salary="2800"),
    ],
    requiredMaterials=[
        MaterialItem(description="BLOCK HUECO 15x20x40", unit="pza",
                     quantity="450", cost="18.50"),
    ],
    toolsRequired=[
        ToolItem(description="REVOLVEDORA DE 1 SACO", unit="pza",
                 quantity="1", cost="850"),
    ],
    specialEquipment=[
        EquipmentItem(description="ANDAMIO TUBULAR", unit="dia",
                      quantity="4", days="6", cost="120"),
    ],
    viaticosTable=[],
)

RESPUESTA_AGENCIA = {
    "success": True,
    "levantamiento": "Muro de block, 30 m2.",
    "calculo": "## Materiales e Insumos\n- BLOCK HUECO: 450 pza",
    "precios": "## TOTAL ESTIMADO DEL PROYECTO: MXN 28,855.00",
    "estructuracion": "Muro de block de 30 m2.",
    "arquitectura_3d_json": "",
    "structured_data": json.dumps(ESTIMACION.model_dump()),
}


@pytest.fixture
def pagina():
    """Una pestaña con la Pre Work Order abierta y la agencia simulada."""
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
            # La agencia real necesita GROQ_API_KEY y varios minutos de LLM. Lo
            # que se prueba aquí es el tramo que falla —lo que el formulario
            # hace con la respuesta—, así que la llamada se sustituye por la
            # respuesta literal que el backend produce.
            page.evaluate(
                "(respuesta) => { ApiService.runPaperclipAgents = async () => respuesta; }",
                RESPUESTA_AGENCIA)
            yield page
        finally:
            navegador.close()


def _app(page):
    return ("document.querySelector('#app').__vue_app__._instance.proxy")


def _correr_agencia(page, descripcion=DISENO):
    page.fill("#campoConcepto", descripcion)
    page.evaluate(f"async () => {{ await {_app(page)}.runPaperclipAgents(); }}")
    page.wait_for_function(f"() => {_app(page)}.isPaperclipRunning === false",
                           timeout=20000)


def _tabla(page, nombre):
    return page.evaluate(
        f"() => JSON.parse(JSON.stringify({_app(page)}.{nombre}.items))")


def _codigo_de_index() -> str:
    """`index.html` sin sus líneas de comentario.

    El texto de esta prueba cita las claves muertas para explicar la
    regresión, y el propio `index.html` las cita en el comentario que
    documenta el arreglo. Buscarlas en el archivo entero daría un falso
    positivo sobre una explicación; lo que se vigila es el código.
    """
    with open("index.html", encoding="utf-8") as fuente:
        lineas = fuente.read().splitlines()
    return "\n".join(linea for linea in lineas
                     if not linea.lstrip().startswith("//"))


# ----------------------------------------------------------------------
# 1. Lo que el agente emite es lo que el formulario lee
# ----------------------------------------------------------------------

def test_el_json_del_agente_trae_las_cuatro_tablas_del_formulario():
    """El contrato, en un solo sitio: las claves del JSON de la agencia."""
    claves = set(ESTIMACION.model_dump())
    assert claves == {"laborTable", "requiredMaterials", "toolsRequired",
                      "specialEquipment", "viaticosTable"}


@pytest.mark.parametrize("clave_muerta", [
    "parsedData.materiales", "parsedData.herramientas",
    "parsedData.mano_de_obra", "parsedData.equipos",
])
def test_el_formulario_ya_no_busca_claves_que_el_agente_nunca_manda(clave_muerta):
    """
    La regresión, congelada: ninguna de estas cuatro claves existe en la
    respuesta de `run_paperclip_agency`, y mientras el formulario las buscara
    las tablas se quedaban vacías sin decir por qué.
    """
    assert clave_muerta not in _codigo_de_index(), (
        f"`{clave_muerta}` no existe en el JSON de la agencia: la estimación "
        f"se pierde en silencio")


# ----------------------------------------------------------------------
# 2. Las tres tablas que pidió el dueño, más el equipo especial
# ----------------------------------------------------------------------

def test_los_materiales_estimados_llegan_a_materiales_requeridos(pagina):
    _correr_agencia(pagina)

    filas = [f for f in _tabla(pagina, "requiredMaterials")
             if f.get("description") == "BLOCK HUECO 15x20x40"]
    assert filas, "MATERIALES REQUERIDOS se quedó sin la estimación del agente"
    (fila,) = filas
    assert str(fila["quantity"]) == "450"
    assert fila["unit"] == "pza"
    assert str(fila["cost"]) == "18.50"
    assert float(fila["total"]) == pytest.approx(450 * 18.50)


def test_las_herramientas_estimadas_llegan_a_herramientas_requeridas(pagina):
    _correr_agencia(pagina)

    filas = [f for f in _tabla(pagina, "toolsRequired")
             if f.get("description") == "REVOLVEDORA DE 1 SACO"]
    assert filas, "HERRAMIENTAS REQUERIDAS se quedó sin la estimación del agente"
    (fila,) = filas
    assert str(fila["quantity"]) == "1"
    assert fila["unit"] == "pza"
    assert float(fila["total"]) == pytest.approx(850.0)


def test_la_mano_de_obra_estimada_llega_a_su_tabla(pagina):
    _correr_agencia(pagina)

    filas = [f for f in _tabla(pagina, "laborTable")
             if f.get("category") == "ALBAÑIL"]
    assert filas, "MANO DE OBRA se quedó sin la estimación del agente"
    (fila,) = filas
    assert str(fila["personnel"]) == "3"
    assert str(fila["weeks"]) == "2"
    assert str(fila["salary"]) == "2800"
    # `updateLaborRowTotal`: salario x personas x semanas, sin extras.
    assert float(fila["total"]) == pytest.approx(2800 * 3 * 2)


def test_el_equipo_especial_estimado_llega_a_su_tabla(pagina):
    _correr_agencia(pagina)

    filas = [f for f in _tabla(pagina, "specialEquipment")
             if f.get("description") == "ANDAMIO TUBULAR"]
    assert filas, "EQUIPO ESPECIAL se quedó sin la estimación del agente"
    (fila,) = filas
    assert str(fila["quantity"]) == "4"
    assert str(fila["days"]) == "6"
    # `updateSpecialEquipRowTotal`: cantidad x días x costo.
    assert float(fila["total"]) == pytest.approx(4 * 6 * 120)


def test_la_estimacion_se_ve_en_la_pantalla(pagina):
    """
    No basta con que el arreglo tenga la fila: el usuario la tiene que ver.
    Las tablas pintan `description` con `v-model`, así que se comprueba el
    valor del input, no el texto del nodo.
    """
    _correr_agencia(pagina)

    valores = pagina.evaluate(
        "() => Array.from(document.querySelectorAll('input'))"
        ".map(i => i.value)")
    for esperado in ("BLOCK HUECO 15x20x40", "REVOLVEDORA DE 1 SACO",
                     "ALBAÑIL", "ANDAMIO TUBULAR"):
        assert esperado in valores, f"'{esperado}' no se ve en el formulario"


# ----------------------------------------------------------------------
# 3. La misma estimación, pedida desde una actividad
# ----------------------------------------------------------------------

def test_la_estimacion_de_una_actividad_queda_marcada_en_esa_actividad(pagina):
    """
    El modal de recursos filtra por `activityId`. Una fila marcada con
    cualquier otro nombre de campo existe en el arreglo pero no se ve en
    ninguna parte, que es peor que no insertarla.
    """
    pagina.evaluate(
        f"() => {{ const app = {_app(pagina)};"
        " app.currentActivityContext = { id: 'ACT-1', description: 'MURO',"
        " dictado: 'Muro de block de 10 x 3 m' };"
        " app.showResourceModal = true; }")
    pagina.evaluate(
        f"async () => {{ await {_app(pagina)}.runActivityPaperclipAgents(); }}")
    pagina.wait_for_function(
        f"() => {_app(pagina)}.isActivityPaperclipRunning === false",
        timeout=20000)

    for tabla, campo, valor in (
        ("requiredMaterials", "description", "BLOCK HUECO 15x20x40"),
        ("toolsRequired", "description", "REVOLVEDORA DE 1 SACO"),
        ("laborTable", "category", "ALBAÑIL"),
        ("specialEquipment", "description", "ANDAMIO TUBULAR"),
    ):
        filas = [f for f in _tabla(pagina, tabla) if f.get(campo) == valor]
        assert filas, f"{tabla}: la actividad se quedó sin su estimación"
        assert filas[0].get("activityId") == "ACT-1", (
            f"{tabla}: la fila no queda ligada a la actividad y el modal de "
            f"recursos no la muestra")


# ----------------------------------------------------------------------
# 4. El aviso dice lo que de verdad entró
# ----------------------------------------------------------------------
# El defecto original era mudo porque el mensaje era fijo: «Análisis
# completado» sobre cero filas se ve exactamente igual que sobre veinte, y por
# eso pudo pasar semanas sin que nadie lo llamara un error. El aviso ahora
# cuenta las filas, así que la próxima vez que la estimación llegue vacía se
# nota en la primera corrida.

def _espiar_avisos(page):
    page.evaluate(
        "() => { window.__avisos = [];"
        " const original = Swal.fire;"
        " Swal.fire = (opciones) => { window.__avisos.push(opciones);"
        "   return Promise.resolve({ isConfirmed: true }); }; }")


def _avisos(page):
    return page.evaluate("() => window.__avisos")


def test_el_aviso_nombra_los_recursos_que_se_insertaron(pagina):
    _espiar_avisos(pagina)
    _correr_agencia(pagina)

    (aviso,) = [a for a in _avisos(pagina) if a.get("icon") == "success"]
    assert "1 materiales" in aviso["text"]
    assert "1 herramientas" in aviso["text"]
    assert "1 de mano de obra" in aviso["text"]
    assert "1 equipos" in aviso["text"]


def test_una_estimacion_vacia_se_avisa_en_vez_de_celebrarse(pagina):
    """
    Cero filas no es un éxito. Sin esto vuelve a existir el modo de fallo que
    originó esta prueba: aviso verde, tablas intactas y nadie enterado.
    """
    vacia = StructuredAgencyData(
        laborTable=[], requiredMaterials=[], toolsRequired=[],
        specialEquipment=[], viaticosTable=[])
    pagina.evaluate(
        "(respuesta) => { ApiService.runPaperclipAgents = async () => respuesta; }",
        dict(RESPUESTA_AGENCIA, structured_data=json.dumps(vacia.model_dump())))
    _espiar_avisos(pagina)
    _correr_agencia(pagina)

    (aviso,) = _avisos(pagina)
    assert aviso["icon"] == "warning"
    assert "no trajo ningún recurso" in aviso["text"]
