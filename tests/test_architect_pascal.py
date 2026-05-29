"""Verifica que architect_node produce JSON compatible con Pascal Editor useScene store."""
import json
import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from langchain_core.runnables import RunnableLambda

from api.paperclip_agents import (
    architect_node,
    integrador_node,
    _build_pascal_scene,
    _default_room_scene,
    WallSegment,
    Opening,
    ArchitectExtraction,
    StructuredAgencyData,
)


class FakeLLM:
    """Mimics base LLM that exposes with_structured_output returning a Runnable."""
    def __init__(self, extraction=None, raise_on_invoke=False):
        self._extraction = extraction
        self._raise = raise_on_invoke

    def with_structured_output(self, _schema):
        if self._raise:
            def boom(_):
                raise RuntimeError("LLM down")
            return RunnableLambda(boom)
        return RunnableLambda(lambda _: self._extraction)


def _assert_pascal_shape(parsed):
    assert set(parsed.keys()) == {"nodes", "rootNodeIds"}, f"Top-level keys wrong: {parsed.keys()}"
    assert isinstance(parsed["nodes"], dict), "nodes must be a dict keyed by id"
    assert isinstance(parsed["rootNodeIds"], list) and len(parsed["rootNodeIds"]) >= 1
    root_id = parsed["rootNodeIds"][0]
    assert root_id in parsed["nodes"], "rootNodeIds[0] missing from nodes dict"
    assert parsed["nodes"][root_id]["type"] == "site"
    # Every node has required fields
    for nid, node in parsed["nodes"].items():
        assert node["id"] == nid
        assert "type" in node
        assert "object" in node and node["object"] == "node"


def test_happy_path_with_llm_extraction():
    extraction = ArchitectExtraction(
        walls=[
            WallSegment(start=[-3, -2], end=[3, -2]),
            WallSegment(start=[3, -2], end=[3, 2]),
            WallSegment(start=[3, 2], end=[-3, 2]),
            WallSegment(start=[-3, 2], end=[-3, -2]),
        ],
        ceiling_height=3.0,
    )
    llm = FakeLLM(extraction=extraction)
    state = {"levantamiento_data": "Habitacion rectangular 6x4 m"}
    result = architect_node(state, llm)

    parsed = json.loads(result["architect_data"])
    _assert_pascal_shape(parsed)

    walls = [n for n in parsed["nodes"].values() if n["type"] == "wall"]
    assert len(walls) == 4, f"Expected 4 walls, got {len(walls)}"
    ceilings = [n for n in parsed["nodes"].values() if n["type"] == "ceiling"]
    assert ceilings[0]["height"] == 3.0


def test_fallback_when_llm_fails():
    llm = FakeLLM(raise_on_invoke=True)
    state = {"levantamiento_data": "anything"}
    result = architect_node(state, llm)

    parsed = json.loads(result["architect_data"])
    _assert_pascal_shape(parsed)
    walls = [n for n in parsed["nodes"].values() if n["type"] == "wall"]
    assert len(walls) == 4, "Fallback room should be 4 walls"


def test_default_room_directly():
    scene = _default_room_scene()
    parsed = json.loads(json.dumps(scene))  # round-trip
    _assert_pascal_shape(parsed)


def test_build_scene_minimal():
    walls = [WallSegment(start=[0, 0], end=[5, 0])]
    scene = _build_pascal_scene(walls, ceiling_height=2.7)
    _assert_pascal_shape(scene)
    # Wall count == 1
    walls_out = [n for n in scene["nodes"].values() if n["type"] == "wall"]
    assert len(walls_out) == 1


def test_openings_doors_and_windows():
    """Una puerta y una ventana deben generar nodos door/window anclados a su muro."""
    walls = [
        WallSegment(start=[-2.5, -5], end=[2.5, -5]),
        WallSegment(start=[2.5, -5], end=[2.5, 5]),
        WallSegment(start=[2.5, 5], end=[-2.5, 5]),
        WallSegment(start=[-2.5, 5], end=[-2.5, -5]),
    ]
    openings = [
        Opening(wall_index=1, kind="door", width=0.9, height=2.1),
        Opening(wall_index=2, kind="window", width=1.2, height=1.2, sill_height=0.9),
    ]
    scene = _build_pascal_scene(walls, 2.5, openings)
    _assert_pascal_shape(scene)

    doors = [n for n in scene["nodes"].values() if n["type"] == "door"]
    windows = [n for n in scene["nodes"].values() if n["type"] == "window"]
    assert len(doors) == 1 and len(windows) == 1

    # Cada abertura está anclada a un muro y listada en sus children.
    for op in doors + windows:
        wall_id = op["parentId"]
        assert wall_id in scene["nodes"] and scene["nodes"][wall_id]["type"] == "wall"
        assert op["id"] in scene["nodes"][wall_id]["children"]
        assert op["wallId"] == wall_id


def test_offset_clamped_into_wall():
    """Un offset fuera del muro se recorta para que la abertura no se salga."""
    walls = [WallSegment(start=[0, 0], end=[4, 0])]
    openings = [Opening(wall_index=1, kind="door", width=1.0, height=2.1, offset=999)]
    scene = _build_pascal_scene(walls, 2.5, openings)
    door = [n for n in scene["nodes"].values() if n["type"] == "door"][0]
    # offset recortado a length - width/2 = 4 - 0.5 = 3.5
    assert door["position"][0] == 3.5


def test_no_openings_backward_compatible():
    """Sin aberturas la escena queda igual que antes (solo muros/slab/ceiling)."""
    walls = [WallSegment(start=[0, 0], end=[5, 0])]
    scene = _build_pascal_scene(walls, 2.7)
    assert not [n for n in scene["nodes"].values() if n["type"] in ("door", "window")]


# --- Regresión: la escena 3D no debe perderse si el integrador falla ---

def test_integrador_failure_preserves_architecture():
    """Si la extracción estructurada del integrador falla, la escena del
    arquitecto debe sobrevivir en arquitectura_3d_json (no quedar en blanco)."""
    scene_json = json.dumps(_default_room_scene())
    state = {
        "architect_data": scene_json,
        "calculo_data": "x",
        "precios_data": "y",
    }
    llm = FakeLLM(raise_on_invoke=True)
    out = integrador_node(state, llm)

    sd = json.loads(out["structured_data"])
    assert sd["arquitectura_3d_json"] == scene_json, "El integrador borró la escena 3D al fallar"
    # Y la escena preservada sigue siendo un JSON Pascal válido
    _assert_pascal_shape(json.loads(sd["arquitectura_3d_json"]))


def test_integrador_success_includes_architecture():
    """En el camino feliz, la escena del arquitecto también se incrusta."""
    scene_json = json.dumps(_default_room_scene())
    state = {
        "architect_data": scene_json,
        "calculo_data": "x",
        "precios_data": "y",
    }
    agency = StructuredAgencyData(
        laborTable=[], requiredMaterials=[], toolsRequired=[],
        specialEquipment=[], viaticosTable=[],
    )
    llm = FakeLLM(extraction=agency)
    out = integrador_node(state, llm)

    sd = json.loads(out["structured_data"])
    assert sd["arquitectura_3d_json"] == scene_json
    _assert_pascal_shape(json.loads(sd["arquitectura_3d_json"]))


if __name__ == "__main__":
    tests = [
        ("happy_path_with_llm_extraction", test_happy_path_with_llm_extraction),
        ("fallback_when_llm_fails", test_fallback_when_llm_fails),
        ("default_room_directly", test_default_room_directly),
        ("build_scene_minimal", test_build_scene_minimal),
        ("openings_doors_and_windows", test_openings_doors_and_windows),
        ("offset_clamped_into_wall", test_offset_clamped_into_wall),
        ("no_openings_backward_compatible", test_no_openings_backward_compatible),
        ("integrador_failure_preserves_architecture", test_integrador_failure_preserves_architecture),
        ("integrador_success_includes_architecture", test_integrador_success_includes_architecture),
    ]
    failed = 0
    for name, fn in tests:
        try:
            fn()
            print(f"PASS  {name}")
        except Exception as e:
            failed += 1
            print(f"FAIL  {name}: {e}")
    if failed:
        sys.exit(1)
