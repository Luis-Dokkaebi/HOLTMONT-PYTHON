"""Verifica los agentes de texto estructurados: levantamiento, cálculo y precios.

Cubre: extracción estructurada -> serialización a texto, validación de
cantidades/precios (> 0), cálculo de totales EN CÓDIGO y fallback a prosa.
"""
import json
import sys
import os

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from langchain_core.runnables import RunnableLambda

from api.paperclip_agents import (
    levantamiento_node,
    calculo_node,
    precios_node,
    evaluador_node,
    route_after_evaluacion,
    _to_float,
    _compute_precios,
    _normalize_calculo,
    _levantamiento_to_text,
    LevantamientoData,
    CalculoData,
    ConceptItem,
    CalculoMaterial,
    CalculoLabor,
    CalculoEquipment,
    PreciosData,
    PrecioItem,
    PreciosCritique,
    MAX_PRECIOS_REVISIONS,
)


class FakeLLM:
    """LLM simulado: structured output devuelve `result`; prosa devuelve objeto con .content."""

    def __init__(self, result=None, raise_structured=False, prose_content="PROSA FALLBACK"):
        self._result = result
        self._raise = raise_structured
        self._prose = prose_content

    def with_structured_output(self, _schema):
        if self._raise:
            def boom(_):
                raise RuntimeError("structured down")
            return RunnableLambda(boom)
        return RunnableLambda(lambda _: self._result)

    # La cadena de prosa hace (prompt | llm); LangChain coacciona un callable a Runnable.
    def __call__(self, *_args, **_kwargs):
        resp = type("_Resp", (), {})()
        resp.content = self._prose
        return resp

    def invoke(self, *_args, **_kwargs):
        return self.__call__()


# ---------- _to_float ----------
def test_to_float_parses_dirty_strings():
    assert _to_float("$1,250.50") == 1250.50
    assert _to_float("3 pza") == 3.0
    assert _to_float("") == 0.0
    assert _to_float(None) == 0.0
    assert _to_float("abc", default=5.0) == 5.0


# ---------- Levantamiento ----------
def test_levantamiento_structured_to_text():
    data = LevantamientoData(
        site_conditions=["Terreno plano"],
        scope=["Construir muro de 10 m"],
        restrictions=["Acceso limitado"],
        missing_info=["Falta altura del muro"],
    )
    res = levantamiento_node({"user_request": "x"}, FakeLLM(result=data))
    txt = res["levantamiento_data"]
    assert "Condiciones del Sitio" in txt
    assert "Terreno plano" in txt
    assert "Falta altura del muro" in txt
    assert "requiere aclaración" in txt


def test_levantamiento_empty_missing_info_shows_placeholder():
    data = LevantamientoData(site_conditions=[], scope=[], restrictions=[], missing_info=[])
    txt = _levantamiento_to_text(data)
    assert "información suficiente" in txt.lower()


def test_levantamiento_fallback_to_prose():
    llm = FakeLLM(raise_structured=True, prose_content="Reporte en prosa")
    res = levantamiento_node({"user_request": "x"}, llm)
    assert res["levantamiento_data"] == "Reporte en prosa"


# ---------- Cálculo ----------
def test_calculo_normalizes_zero_quantities():
    data = CalculoData(
        concepts=[ConceptItem(concept="Muro", unit="m2", quantity="0")],
        materials=[CalculoMaterial(description="Cemento", unit="bulto", quantity="")],
        labor=[CalculoLabor(role="Albañil", people="0", duration="0", unit="raro")],
        equipment=[CalculoEquipment(description="Mezcladora", quantity="-3")],
    )
    fixed = _normalize_calculo(data)
    assert fixed.concepts[0].quantity == "1"
    assert fixed.materials[0].quantity == "1"
    assert fixed.labor[0].people == "1"
    assert fixed.labor[0].duration == "1"
    assert fixed.labor[0].unit == "dia"  # unidad inválida -> dia
    assert fixed.equipment[0].quantity == "1"


def test_calculo_node_produces_sections():
    data = CalculoData(
        concepts=[ConceptItem(concept="Losa", unit="m2", quantity="20")],
        materials=[CalculoMaterial(description="Varilla", unit="pza", quantity="50")],
        labor=[CalculoLabor(role="Fierrero", people="2", duration="3", unit="dia")],
        equipment=[],
    )
    res = calculo_node({"levantamiento_data": "x"}, FakeLLM(result=data))
    txt = res["calculo_data"]
    assert "Catálogo de Conceptos" in txt
    assert "Varilla" in txt
    assert "Fierrero: 2 persona(s) x 3 dia" in txt


def test_calculo_fallback_to_prose():
    llm = FakeLLM(raise_structured=True, prose_content="Calculo prosa")
    res = calculo_node({"levantamiento_data": "x"}, llm)
    assert res["calculo_data"] == "Calculo prosa"


# ---------- Precios ----------
def test_precios_totals_computed_in_code():
    data = PreciosData(currency="MXN", items=[
        PrecioItem(category="material", description="Cemento", unit="bulto", quantity="10", unit_price="200"),
        PrecioItem(category="mano_obra", description="Albañil", unit="dia", quantity="5", unit_price="800"),
    ])
    computed = _compute_precios(data)
    # 10*200 + 5*800 = 2000 + 4000 = 6000
    assert computed["grand_total"] == 6000.0
    assert computed["grupos"]["material"][0]["line_total"] == 2000.0
    assert computed["grupos"]["mano_obra"][0]["line_total"] == 4000.0


def test_precios_forces_positive_price_and_qty():
    data = PreciosData(items=[
        PrecioItem(category="material", description="X", unit="pza", quantity="0", unit_price="0"),
    ])
    computed = _compute_precios(data)
    # qty y price forzados a 1 -> total 1
    assert computed["grand_total"] == 1.0


def test_precios_node_renders_total_line():
    data = PreciosData(currency="MXN", items=[
        PrecioItem(category="material", description="Tabique", unit="pza", quantity="100", unit_price="5"),
    ])
    res = precios_node({"calculo_data": "x"}, FakeLLM(result=data))
    txt = res["precios_data"]
    assert "TOTAL ESTIMADO DEL PROYECTO" in txt
    assert "500.00" in txt  # 100 * 5


def test_precios_fallback_to_prose():
    llm = FakeLLM(raise_structured=True, prose_content="Precios prosa")
    res = precios_node({"calculo_data": "x"}, llm)
    assert res["precios_data"] == "Precios prosa"


def test_precios_uses_critique_when_present():
    """Si hay crítica previa, precios_node sigue produciendo presupuesto válido."""
    data = PreciosData(items=[
        PrecioItem(category="material", description="Y", unit="pza", quantity="2", unit_price="50"),
    ])
    state = {"calculo_data": "x", "precios_critique": "Faltó incluir el cemento"}
    res = precios_node(state, FakeLLM(result=data))
    assert "TOTAL ESTIMADO" in res["precios_data"]
    assert "100.00" in res["precios_data"]  # 2 * 50


# ---------- Evaluador + loop de reflexión ----------
def test_evaluador_approves():
    verdict = PreciosCritique(is_approved=True, critique="")
    state = {"calculo_data": "c", "precios_data": "p", "precios_revision": 0}
    res = evaluador_node(state, FakeLLM(result=verdict))
    assert res["precios_approved"] is True
    assert res["precios_revision"] == 1


def test_evaluador_rejects_with_critique():
    verdict = PreciosCritique(is_approved=False, critique="Falta el acero de refuerzo")
    state = {"calculo_data": "c", "precios_data": "p", "precios_revision": 0}
    res = evaluador_node(state, FakeLLM(result=verdict))
    assert res["precios_approved"] is False
    assert "acero" in res["precios_critique"]
    assert res["precios_revision"] == 1


def test_evaluador_fallback_approves_on_error():
    """Si el evaluador falla, no debe bloquear el pipeline."""
    res = evaluador_node({"calculo_data": "c", "precios_data": "p", "precios_revision": 0},
                         FakeLLM(raise_structured=True))
    assert res["precios_approved"] is True


def test_route_approved_goes_to_integrador():
    assert route_after_evaluacion({"precios_approved": True, "precios_revision": 1}) == "integrador"


def test_route_rejected_goes_back_to_precios():
    assert route_after_evaluacion({"precios_approved": False, "precios_revision": 1}) == "precios"


def test_route_exhausted_revisions_goes_to_integrador():
    """Aunque rechace, al agotar revisiones avanza a integrador (loop acotado)."""
    state = {"precios_approved": False, "precios_revision": MAX_PRECIOS_REVISIONS + 1}
    assert route_after_evaluacion(state) == "integrador"
