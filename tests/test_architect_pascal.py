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
    DoorOpening,
    WindowOpening,
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


def test_door_and_window_nodes_created():
    """Puertas y ventanas deben aparecer como nodos en la escena con parentId = su muro."""
    walls = [
        WallSegment(start=[-2.5, -5], end=[2.5, -5]),   # wall 0 — puerta aquí
        WallSegment(start=[2.5, -5], end=[2.5, 5]),     # wall 1 — ventana aquí
        WallSegment(start=[2.5, 5], end=[-2.5, 5]),
        WallSegment(start=[-2.5, 5], end=[-2.5, -5]),
    ]
    doors = [DoorOpening(wall_index=0, position_along_wall=0.5, width=0.9, height=2.1)]
    windows = [WindowOpening(wall_index=1, position_along_wall=0.5, width=1.2, height=1.0, sill_height=0.9)]

    scene = _build_pascal_scene(walls, ceiling_height=2.5, doors=doors, windows=windows)
    _assert_pascal_shape(scene)

    nodes = scene["nodes"]
    door_nodes = [n for n in nodes.values() if n["type"] == "door"]
    window_nodes = [n for n in nodes.values() if n["type"] == "window"]

    assert len(door_nodes) == 1, f"Expected 1 door, got {len(door_nodes)}"
    assert len(window_nodes) == 1, f"Expected 1 window, got {len(window_nodes)}"

    # Door/window parentId must be an existing wall node
    wall_ids = {n["id"] for n in nodes.values() if n["type"] == "wall"}
    assert door_nodes[0]["parentId"] in wall_ids, "Door parentId not in wall nodes"
    assert window_nodes[0]["parentId"] in wall_ids, "Window parentId not in wall nodes"

    # Parent walls must list the openings in their children
    door_parent = nodes[door_nodes[0]["parentId"]]
    assert door_nodes[0]["id"] in door_parent["children"]
    window_parent = nodes[window_nodes[0]["parentId"]]
    assert window_nodes[0]["id"] in window_parent["children"]

    # Check door/window fields
    d = door_nodes[0]
    assert d["width"] == 0.9 and d["height"] == 2.1 and d["position"] == 0.5
    w = window_nodes[0]
    assert w["width"] == 1.2 and w["height"] == 1.0 and w["sillHeight"] == 0.9


def test_llm_extraction_with_doors_and_windows():
    """architect_node debe incluir puertas y ventanas en la escena cuando el LLM las extrae."""
    walls = [
        WallSegment(start=[0, 0], end=[5, 0]),
        WallSegment(start=[5, 0], end=[5, 10]),
        WallSegment(start=[5, 10], end=[0, 10]),
        WallSegment(start=[0, 10], end=[0, 0]),
    ]
    extraction = ArchitectExtraction(
        walls=walls,
        ceiling_height=2.5,
        doors=[DoorOpening(wall_index=0, position_along_wall=0.5)],
        windows=[WindowOpening(wall_index=1, position_along_wall=0.5)],
    )
    llm = FakeLLM(extraction=extraction)
    state = {"levantamiento_data": "Cuarto 5x10 con puerta en muro sur y ventana en muro este"}
    result = architect_node(state, llm)

    parsed = json.loads(result["architect_data"])
    _assert_pascal_shape(parsed)

    door_nodes = [n for n in parsed["nodes"].values() if n["type"] == "door"]
    window_nodes = [n for n in parsed["nodes"].values() if n["type"] == "window"]
    assert len(door_nodes) == 1, "architect_node should include 1 door"
    assert len(window_nodes) == 1, "architect_node should include 1 window"


def test_scene_without_openings_has_no_door_window_nodes():
    """Escena sin puertas/ventanas no debe tener nodos de tipo door o window."""
    walls = [
        WallSegment(start=[-2, -2], end=[2, -2]),
        WallSegment(start=[2, -2], end=[2, 2]),
        WallSegment(start=[2, 2], end=[-2, 2]),
        WallSegment(start=[-2, 2], end=[-2, -2]),
    ]
    scene = _build_pascal_scene(walls)
    nodes = scene["nodes"]
    assert not any(n["type"] in ("door", "window") for n in nodes.values())


if __name__ == "__main__":
    tests = [
        ("happy_path_with_llm_extraction", test_happy_path_with_llm_extraction),
        ("fallback_when_llm_fails", test_fallback_when_llm_fails),
        ("default_room_directly", test_default_room_directly),
        ("build_scene_minimal", test_build_scene_minimal),
        ("integrador_failure_preserves_architecture", test_integrador_failure_preserves_architecture),
        ("integrador_success_includes_architecture", test_integrador_success_includes_architecture),
        ("door_and_window_nodes_created", test_door_and_window_nodes_created),
        ("llm_extraction_with_doors_and_windows", test_llm_extraction_with_doors_and_windows),
        ("scene_without_openings_has_no_door_window_nodes", test_scene_without_openings_has_no_door_window_nodes),
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
