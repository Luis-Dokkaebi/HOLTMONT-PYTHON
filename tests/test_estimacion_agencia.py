"""La estimación de la Agencia Paperclip llega a las tablas, y no depende de un LLM.

Reporte del dueño (2026-09-08, segunda vez):

    «El agente que hace las estimaciones en la prework order aún no funciona de
    manera correcta, no está arrojando ni escribiendo los datos en Mano de
    obra/herramientas y materiales.»

El arreglo anterior (5d18efc) corrigió el formulario: leía claves que el agente
no manda. Se probó todo ese tramo con la respuesta del backend simulada, y ahí
quedó el hueco: **nadie probó que el backend produjera esa respuesta**.

Y no la producía de forma confiable. Las cuatro tablas salían de UNA sola
llamada al modelo —el Integrador releyendo la prosa de los agentes anteriores
con el esquema más grande del archivo, `StructuredAgencyData`, cinco listas
anidadas—, sin reintento (a diferencia del resto de los nodos, que usan
`_invoke_structured`) y sin respaldo. Si esa llamada fallaba, o si el modelo se
rendía devolviendo las cinco listas vacías, `structured_data` salía vacío, el
formulario insertaba cero filas y el usuario veía exactamente lo que reportó:
tablas intactas.

Lo absurdo es que el dato ya estaba estructurado antes de esa llamada:
`calculo_node` produce un `CalculoData` y `precios_node` un `PreciosData` con
categoría, unidad, cantidad y precio unitario de cada concepto. Se serializaban
a markdown y se tiraba la estructura para pedirle a un modelo que la volviera a
extraer de su propio texto.

Estas pruebas fijan el contrato del lado del backend: si la agencia calculó un
presupuesto, las tablas se llenan — aunque el Integrador falle, aunque devuelva
vacío, y sin depender de que un modelo acierte a leer su propia prosa.
"""

from __future__ import annotations

import json
import os
import sys

import pytest
from unittest import mock

from langchain_core.runnables import RunnableLambda

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from api.paperclip_agents import (  # noqa: E402
    CalculoData,
    CalculoEquipment,
    CalculoLabor,
    CalculoMaterial,
    ConceptItem,
    LevantamientoData,
    PrecioItem,
    PreciosCritique,
    PreciosData,
    StructuredAgencyData,
    _compute_precios,
    build_paperclip_graph,
    calculo_node,
    estimacion_desde_estructura,
    estimacion_vacia,
    integrador_node,
    precios_node,
)

# --- Los datos de una obra pequeña, como los produce la propia agencia -------

CALCULO = CalculoData(
    concepts=[ConceptItem(concept="Muro de block", unit="m2", quantity="30")],
    materials=[
        CalculoMaterial(description="Block hueco 15x20x40", unit="pza", quantity="450"),
        CalculoMaterial(description="Cemento gris", unit="bulto", quantity="12"),
    ],
    labor=[CalculoLabor(role="Albañil", people="3", duration="2", unit="semana")],
    equipment=[CalculoEquipment(description="Andamio tubular", quantity="4")],
)

PRECIOS = PreciosData(currency="MXN", items=[
    PrecioItem(category="material", description="Block hueco 15x20x40",
               unit="pza", quantity="450", unit_price="18.50"),
    PrecioItem(category="material", description="Cemento gris",
               unit="bulto", quantity="12", unit_price="220"),
    PrecioItem(category="mano_obra", description="Albañil",
               unit="semana", quantity="6", unit_price="2800"),
    PrecioItem(category="herramienta", description="Revolvedora de 1 saco",
               unit="pza", quantity="1", unit_price="850"),
    PrecioItem(category="equipo", description="Andamio tubular",
               unit="dia", quantity="24", unit_price="120"),
])

COMPUTADO = _compute_precios(PRECIOS)


class LLMFalso:
    """LLM simulado. `fallas` nombra los esquemas cuya extracción revienta."""

    def __init__(self, respuestas=None, fallas=(), prosa="PROSA"):
        self._respuestas = respuestas or {}
        self._fallas = tuple(fallas)
        self._prosa = prosa

    def with_structured_output(self, schema):
        if schema in self._fallas:
            def revienta(_):
                raise RuntimeError(f"structured output caído para {schema.__name__}")
            return RunnableLambda(revienta)
        if schema not in self._respuestas:
            def sin_respuesta(_):
                raise RuntimeError(f"sin respuesta simulada para {schema.__name__}")
            return RunnableLambda(sin_respuesta)
        return RunnableLambda(lambda _: self._respuestas[schema])

    def invoke(self, *_a, **_k):
        respuesta = type("_Resp", (), {})()
        respuesta.content = self._prosa
        return respuesta

    def __call__(self, *_a, **_k):
        return self.invoke()


def _fila(filas, campo, valor):
    encontradas = [f for f in filas if getattr(f, campo) == valor]
    assert encontradas, f"no hay fila con {campo} = {valor!r}"
    return encontradas[0]


# ----------------------------------------------------------------------
# 1. La estimación se arma con lo que la agencia ya calculó
# ----------------------------------------------------------------------

def test_los_materiales_del_presupuesto_llegan_con_cantidad_y_costo():
    estimacion = estimacion_desde_estructura(CALCULO, COMPUTADO)

    block = _fila(estimacion.requiredMaterials, "description", "Block hueco 15x20x40")
    assert block.quantity == "450"
    assert block.unit == "pza"
    assert block.cost == "18.5"
    # La tabla del formulario multiplica cantidad x costo.
    assert float(block.quantity) * float(block.cost) == pytest.approx(8325.0)


def test_las_herramientas_del_presupuesto_llegan_a_su_tabla():
    estimacion = estimacion_desde_estructura(CALCULO, COMPUTADO)

    revolvedora = _fila(estimacion.toolsRequired, "description", "Revolvedora de 1 saco")
    assert revolvedora.quantity == "1"
    assert revolvedora.cost == "850"


def test_la_mano_de_obra_cruza_el_precio_con_la_gente_y_el_tiempo():
    """El presupuesto sabe cuánto cuesta la semana; el cálculo, cuánta gente y
    cuántas semanas. La tabla multiplica salario x personal x tiempo, así que
    el precio unitario va como salario y no se mete el personal en el tiempo."""
    estimacion = estimacion_desde_estructura(CALCULO, COMPUTADO)

    albanil = _fila(estimacion.laborTable, "category", "Albañil")
    assert albanil.salary == "2800"
    assert albanil.personnel == "3"
    assert albanil.weeks == "2"
    assert albanil.unit == "semana"
    assert (float(albanil.salary) * float(albanil.personnel)
            * float(albanil.weeks)) == pytest.approx(16800.0)


def test_el_equipo_no_se_cobra_dos_veces():
    """El total de EQUIPO ESPECIAL es cantidad x días x costo y la cantidad del
    presupuesto ya trae el tiempo dentro: los días van en 1."""
    estimacion = estimacion_desde_estructura(CALCULO, COMPUTADO)

    andamio = _fila(estimacion.specialEquipment, "description", "Andamio tubular")
    assert andamio.days == "1"
    assert andamio.quantity == "24"
    assert (float(andamio.quantity) * float(andamio.days)
            * float(andamio.cost)) == pytest.approx(2880.0)


def test_un_concepto_sin_precio_entra_igual_con_costo_en_cero():
    """Una fila visible y en blanco es un pendiente que se ve. Una fila ausente
    es el fallo mudo que originó estas pruebas."""
    calculo = CalculoData(
        concepts=[], materials=[CalculoMaterial(description="Malla electrosoldada",
                                                unit="m2", quantity="30")],
        labor=[], equipment=[])
    estimacion = estimacion_desde_estructura(calculo, _compute_precios(PreciosData(items=[])))

    malla = _fila(estimacion.requiredMaterials, "description", "Malla electrosoldada")
    assert malla.quantity == "30"
    assert malla.cost == "0"


def test_un_puesto_que_solo_esta_en_el_presupuesto_no_infla_el_total():
    """Sin cálculo que diga cuánta gente es, el personal se asume en 1 y la
    cantidad presupuestada es el tiempo: el total coincide con el presupuesto."""
    precios = _compute_precios(PreciosData(items=[
        PrecioItem(category="mano_obra", description="Soldador",
                   unit="dia", quantity="5", unit_price="1200")]))
    estimacion = estimacion_desde_estructura(None, precios)

    soldador = _fila(estimacion.laborTable, "category", "Soldador")
    assert soldador.personnel == "1"
    assert soldador.weeks == "5"
    assert soldador.salary == "1200"
    assert (float(soldador.salary) * float(soldador.personnel)
            * float(soldador.weeks)) == pytest.approx(6000.0)


def test_el_rol_se_cruza_aunque_el_nombre_no_sea_identico():
    """"Albañil" en el cálculo y "Albañil oficial" en el presupuesto son el
    mismo puesto: sin este cruce la fila quedaba con salario 0."""
    calculo = CalculoData(concepts=[], materials=[], equipment=[],
                          labor=[CalculoLabor(role="Albañil", people="2",
                                              duration="3", unit="dia")])
    precios = _compute_precios(PreciosData(items=[
        PrecioItem(category="mano_obra", description="Albañil oficial",
                   unit="dia", quantity="6", unit_price="900")]))
    estimacion = estimacion_desde_estructura(calculo, precios)

    assert len(estimacion.laborTable) == 1, "el puesto se duplicó"
    assert estimacion.laborTable[0].salary == "900"
    assert estimacion.laborTable[0].personnel == "2"


def test_sin_calculo_ni_precios_la_estimacion_queda_vacia():
    assert estimacion_vacia(estimacion_desde_estructura(None, None))


# ----------------------------------------------------------------------
# 2. El integrador ya no depende de que el modelo acierte
# ----------------------------------------------------------------------

def _estado_con_estructura(**extra):
    estado = {
        "architect_data": "",
        "calculo_data": "texto del cálculo",
        "calculo_struct": CALCULO.model_dump_json(),
        "precios_data": "texto de precios",
        "precios_struct": json.dumps(COMPUTADO),
    }
    estado.update(extra)
    return estado


def test_las_tablas_se_llenan_aunque_la_extraccion_del_modelo_falle():
    """El modo de fallo reportado: el Integrador revienta y el usuario se queda
    con las tablas vacías. Ahora la estimación sale del presupuesto."""
    salida = integrador_node(_estado_con_estructura(),
                             LLMFalso(fallas=(StructuredAgencyData,)))

    datos = json.loads(salida["structured_data"])
    assert salida["estimacion_origen"] == "estructura"
    assert len(datos["requiredMaterials"]) == 2
    assert len(datos["toolsRequired"]) == 1
    assert len(datos["laborTable"]) == 1
    assert len(datos["specialEquipment"]) == 1


def test_las_tablas_se_llenan_aunque_el_modelo_devuelva_todo_vacio():
    """Un modelo que se rinde devuelve las cinco listas vacías sin lanzar nada:
    es el fallo mudo por excelencia y también queda cubierto."""
    vacia = StructuredAgencyData(laborTable=[], requiredMaterials=[], toolsRequired=[],
                                 specialEquipment=[], viaticosTable=[])
    salida = integrador_node(_estado_con_estructura(),
                             LLMFalso(respuestas={StructuredAgencyData: vacia}))

    datos = json.loads(salida["structured_data"])
    assert salida["estimacion_origen"] == "estructura"
    assert datos["requiredMaterials"], "las tablas volvieron vacías"


def test_sin_estructura_el_integrador_todavia_usa_el_modelo():
    """Cuando cálculo y precios cayeron a su respaldo en prosa no hay estructura
    que usar: ahí el LLM sigue siendo el único camino, y debe seguir sirviendo."""
    delModelo = StructuredAgencyData(
        laborTable=[], requiredMaterials=[], toolsRequired=[], specialEquipment=[],
        viaticosTable=[])
    delModelo = StructuredAgencyData.model_validate({
        "laborTable": [{"category": "PINTOR", "personnel": "2", "unit": "dia",
                        "weeks": "4", "salary": "700"}],
        "requiredMaterials": [], "toolsRequired": [], "specialEquipment": [],
        "viaticosTable": []})
    salida = integrador_node(
        {"architect_data": "", "calculo_data": "prosa", "precios_data": "prosa"},
        LLMFalso(respuestas={StructuredAgencyData: delModelo}))

    datos = json.loads(salida["structured_data"])
    assert salida["estimacion_origen"] == "llm"
    assert datos["laborTable"][0]["category"] == "PINTOR"


def test_con_precios_en_prosa_manda_el_modelo():
    """Si `precios_node` cayó a su respaldo en prosa, los precios solo existen
    en el texto: ahí el modelo aporta algo que la estructura no tiene, y se
    usa."""
    delModelo = StructuredAgencyData.model_validate({
        "laborTable": [], "toolsRequired": [], "specialEquipment": [], "viaticosTable": [],
        "requiredMaterials": [{"description": "Block hueco 15x20x40", "unit": "pza",
                               "quantity": "450", "cost": "18.50"}]})
    salida = integrador_node(
        {"architect_data": "", "calculo_data": "texto", "precios_data": "prosa con precios",
         "calculo_struct": CALCULO.model_dump_json(), "precios_struct": ""},
        LLMFalso(respuestas={StructuredAgencyData: delModelo}))

    assert salida["estimacion_origen"] == "llm"
    assert json.loads(salida["structured_data"])["requiredMaterials"][0]["cost"] == "18.50"


def test_sin_precios_y_sin_modelo_entran_los_conceptos_a_capturar_costo():
    """El último recurso antes de la tabla vacía: los conceptos del cálculo con
    costo 0. Un pendiente que se ve vale más que un formulario intacto."""
    salida = integrador_node(
        {"architect_data": "", "calculo_data": "texto", "precios_data": "prosa",
         "calculo_struct": CALCULO.model_dump_json(), "precios_struct": ""},
        LLMFalso(fallas=(StructuredAgencyData,)))

    datos = json.loads(salida["structured_data"])
    assert salida["estimacion_origen"] == "estructura_sin_precios"
    assert [m["description"] for m in datos["requiredMaterials"]] == [
        "Block hueco 15x20x40", "Cemento gris"]
    assert datos["requiredMaterials"][0]["cost"] == "0"
    assert datos["laborTable"][0]["category"] == "Albañil"


def test_cuando_no_se_pudo_estimar_se_dice_y_no_se_finge():
    salida = integrador_node(
        {"architect_data": "", "calculo_data": "prosa", "precios_data": "prosa"},
        LLMFalso(fallas=(StructuredAgencyData,)))

    assert salida["estimacion_origen"] == "vacia"
    assert json.loads(salida["structured_data"])["laborTable"] == []


def test_la_escena_3d_viaja_con_la_estimacion():
    """Un fallo de las tablas no descarta el diseño, y al revés tampoco."""
    salida = integrador_node(_estado_con_estructura(architect_data='{"nodes": {}}'),
                             LLMFalso(fallas=(StructuredAgencyData,)))

    assert json.loads(salida["structured_data"])["arquitectura_3d_json"] == '{"nodes": {}}'


# ----------------------------------------------------------------------
# 3. Los nodos conservan la estructura que las tablas necesitan
# ----------------------------------------------------------------------

def test_el_calculo_guarda_su_estructura_ademas_del_texto():
    salida = calculo_node({"levantamiento_data": "x"},
                          LLMFalso(respuestas={CalculoData: CALCULO}))

    assert "Catálogo de Conceptos" in salida["calculo_data"]
    recuperado = CalculoData.model_validate_json(salida["calculo_struct"])
    assert recuperado.materials[0].description == "Block hueco 15x20x40"


def test_los_precios_guardan_lo_calculado_ademas_del_texto():
    salida = precios_node({"calculo_data": "x"},
                          LLMFalso(respuestas={PreciosData: PRECIOS}))

    computado = json.loads(salida["precios_struct"])
    assert computado["grupos"]["material"][0]["unit_price"] == 18.50
    assert computado["grand_total"] == pytest.approx(COMPUTADO["grand_total"])


# ----------------------------------------------------------------------
# 4. La agencia completa, de punta a punta
# ----------------------------------------------------------------------

def _grafo(fallas=()):
    llm = LLMFalso(
        respuestas={
            LevantamientoData: LevantamientoData(
                site_conditions=["Nave industrial"], scope=["Muro de block de 10 x 3 m"],
                restrictions=[], missing_info=[]),
            CalculoData: CALCULO,
            PreciosData: PRECIOS,
            PreciosCritique: PreciosCritique(is_approved=True, critique=""),
            StructuredAgencyData: StructuredAgencyData(
                laborTable=[], requiredMaterials=[], toolsRequired=[],
                specialEquipment=[], viaticosTable=[]),
        },
        fallas=fallas)
    return build_paperclip_graph(llm, llm)


ESTADO_INICIAL = {
    "user_request": "Muro de block de 10 x 3 m de altura en nave industrial",
    "levantamiento_data": "", "architect_data": "", "architect_origen": "",
    "architect_aviso": "", "calculo_data": "", "calculo_struct": "",
    "precios_data": "", "precios_struct": "", "structured_data": "",
    "estimacion_origen": "", "precios_critique": "", "precios_approved": False,
    "precios_revision": 0,
}


def test_la_agencia_completa_devuelve_las_tablas_llenas():
    final = _grafo().invoke(dict(ESTADO_INICIAL))

    datos = json.loads(final["structured_data"])
    assert final["estimacion_origen"] == "estructura"
    assert [m["description"] for m in datos["requiredMaterials"]] == [
        "Block hueco 15x20x40", "Cemento gris"]
    assert datos["laborTable"][0]["category"] == "Albañil"
    assert datos["toolsRequired"][0]["description"] == "Revolvedora de 1 saco"
    assert datos["specialEquipment"][0]["description"] == "Andamio tubular"


def test_la_agencia_completa_aguanta_que_se_caiga_el_integrador():
    """La corrida que el dueño ve: todo bien hasta la última llamada, que
    revienta. Antes esto vaciaba las tres tablas."""
    final = _grafo(fallas=(StructuredAgencyData,)).invoke(dict(ESTADO_INICIAL))

    datos = json.loads(final["structured_data"])
    assert datos["requiredMaterials"], "MATERIALES REQUERIDOS se quedó vacío"
    assert datos["toolsRequired"], "HERRAMIENTAS REQUERIDAS se quedó vacío"
    assert datos["laborTable"], "MANO DE OBRA se quedó vacío"


def test_las_claves_del_json_son_las_que_lee_el_formulario():
    """El contrato con `index.html`, en una sola aserción."""
    final = _grafo().invoke(dict(ESTADO_INICIAL))

    datos = json.loads(final["structured_data"])
    assert {"requiredMaterials", "toolsRequired", "laborTable",
            "specialEquipment"} <= set(datos)
    material = datos["requiredMaterials"][0]
    assert {"description", "unit", "quantity", "cost"} <= set(material)
    labor = datos["laborTable"][0]
    assert {"category", "personnel", "weeks", "salary", "unit"} <= set(labor)


# ----------------------------------------------------------------------
# 5. La respuesta que sale del backend, tal como la arma `run_paperclip_agency`
# ----------------------------------------------------------------------

def correr_agencia_simulada(fallas=()) -> dict:
    """`run_paperclip_agency` de verdad, con el LLM simulado.

    Lo único que se sustituye es el proveedor: `ChatGroq` (y la clave que exige)
    no existen en una prueba. El grafo, el estado inicial y el ensamblado de la
    respuesta son los de producción, así que si alguien renombra una clave del
    JSON esta prueba —y la de navegador, que la usa— lo ven antes que el
    usuario.
    """
    llm = LLMFalso(
        respuestas={
            LevantamientoData: LevantamientoData(
                site_conditions=["Nave industrial"], scope=["Muro de block de 10 x 3 m"],
                restrictions=[], missing_info=[]),
            CalculoData: CALCULO,
            PreciosData: PRECIOS,
            PreciosCritique: PreciosCritique(is_approved=True, critique=""),
            StructuredAgencyData: StructuredAgencyData(
                laborTable=[], requiredMaterials=[], toolsRequired=[],
                specialEquipment=[], viaticosTable=[]),
        },
        fallas=fallas)

    import api.paperclip_agents as agencia
    with mock.patch.object(agencia, "ChatGroq", lambda **_kw: llm), \
         mock.patch.object(agencia, "ChatGoogleGenerativeAI", None), \
         mock.patch.dict(os.environ, {"GROQ_API_KEY": "prueba", "GEMINI_API_KEY": ""}):
        return agencia.run_paperclip_agency(
            "Muro de block de 10 x 3 m de altura en nave industrial")


def test_la_respuesta_del_backend_trae_la_estimacion_y_su_origen():
    respuesta = correr_agencia_simulada()

    assert respuesta["success"] is True
    assert respuesta["estimacion_origen"] == "estructura"
    datos = json.loads(respuesta["structured_data"])
    assert len(datos["requiredMaterials"]) == 2
    assert len(datos["toolsRequired"]) == 1
    assert len(datos["laborTable"]) == 1


def test_la_respuesta_trae_el_informe_que_el_formulario_escribe():
    """El formulario redacta la Descripción del Trabajo con estas tres claves.
    Leía `estructuracion`, que ninguna respuesta del backend contiene."""
    respuesta = correr_agencia_simulada()

    assert "Condiciones del Sitio" in respuesta["levantamiento"]
    assert "Catálogo de Conceptos" in respuesta["calculo"]
    assert "TOTAL ESTIMADO DEL PROYECTO" in respuesta["precios"]
    assert "estructuracion" not in respuesta


def test_la_respuesta_llega_llena_aunque_se_caiga_el_integrador():
    respuesta = correr_agencia_simulada(fallas=(StructuredAgencyData,))

    datos = json.loads(respuesta["structured_data"])
    assert respuesta["estimacion_origen"] == "estructura"
    assert datos["requiredMaterials"] and datos["toolsRequired"] and datos["laborTable"]


def test_sin_clave_de_groq_la_agencia_lo_dice_en_vez_de_devolver_vacio():
    import api.paperclip_agents as agencia
    with mock.patch.dict(os.environ, {"GROQ_API_KEY": ""}):
        respuesta = agencia.run_paperclip_agency("Muro de block")

    assert respuesta["success"] is False
    assert "GROQ_API_KEY" in respuesta["error"]
