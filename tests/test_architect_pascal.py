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
    _validate_and_fix_extraction,
    WallSegment,
    DoorOpening,
    WindowOpening,
    StaircaseConfig,
    RoofConfig,
    FurnitureItem,
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


# --- Mejora 3: Multi-nivel ---

def test_multi_level_scene():
    """Dos pisos deben generar dos nodos level con sus propios muros."""
    walls = [
        # PB
        WallSegment(start=[0, 0], end=[5, 0], level=0),
        WallSegment(start=[5, 0], end=[5, 4], level=0),
        WallSegment(start=[5, 4], end=[0, 4], level=0),
        WallSegment(start=[0, 4], end=[0, 0], level=0),
        # P1
        WallSegment(start=[0, 0], end=[5, 0], level=1),
        WallSegment(start=[5, 0], end=[5, 4], level=1),
        WallSegment(start=[5, 4], end=[0, 4], level=1),
        WallSegment(start=[0, 4], end=[0, 0], level=1),
    ]
    scene = _build_pascal_scene(walls, num_levels=2)
    _assert_pascal_shape(scene)
    nodes = scene["nodes"]

    level_nodes = [n for n in nodes.values() if n["type"] == "level"]
    assert len(level_nodes) == 2, f"Expected 2 levels, got {len(level_nodes)}"
    level_indices = sorted(n["level"] for n in level_nodes)
    assert level_indices == [0, 1]

    walls_out = [n for n in nodes.values() if n["type"] == "wall"]
    assert len(walls_out) == 8


# --- Mejora 2: Escaleras ---

def test_staircase_node_created():
    """Escalera debe existir como nodo hijo del nivel de origen."""
    walls = [
        WallSegment(start=[0, 0], end=[6, 0], level=0),
        WallSegment(start=[6, 0], end=[6, 4], level=0),
        WallSegment(start=[6, 4], end=[0, 4], level=0),
        WallSegment(start=[0, 4], end=[0, 0], level=0),
        WallSegment(start=[0, 0], end=[6, 0], level=1),
        WallSegment(start=[6, 0], end=[6, 4], level=1),
        WallSegment(start=[6, 4], end=[0, 4], level=1),
        WallSegment(start=[0, 4], end=[0, 0], level=1),
    ]
    stairs = [StaircaseConfig(position=[4.0, 1.0], width=1.0, steps=12,
                               direction="north", from_level=0, to_level=1)]
    scene = _build_pascal_scene(walls, num_levels=2, staircases=stairs)
    _assert_pascal_shape(scene)
    nodes = scene["nodes"]

    stair_nodes = [n for n in nodes.values() if n["type"] == "staircase"]
    assert len(stair_nodes) == 1, f"Expected 1 staircase, got {len(stair_nodes)}"
    s = stair_nodes[0]
    assert s["fromLevel"] == 0 and s["toLevel"] == 1
    assert s["steps"] == 12 and s["direction"] == "north"

    # Debe ser hijo del nivel 0
    level_0 = next(n for n in nodes.values() if n["type"] == "level" and n["level"] == 0)
    assert s["id"] in level_0["children"]


# --- Mejora 2: Techo inclinado ---

def test_gabled_roof_node_on_top_level():
    """Techo 'gabled' debe generar nodo tipo roof en nivel superior, no ceiling."""
    walls = [
        WallSegment(start=[-3, -2], end=[3, -2]),
        WallSegment(start=[3, -2], end=[3, 2]),
        WallSegment(start=[3, 2], end=[-3, 2]),
        WallSegment(start=[-3, 2], end=[-3, -2]),
    ]
    roof = RoofConfig(roof_type="gabled", pitch=35.0, overhang=0.6)
    scene = _build_pascal_scene(walls, roof=roof)
    _assert_pascal_shape(scene)
    nodes = scene["nodes"]

    roof_nodes = [n for n in nodes.values() if n["type"] == "roof"]
    ceiling_nodes = [n for n in nodes.values() if n["type"] == "ceiling"]
    assert len(roof_nodes) == 1, "Expected 1 roof node for gabled roof"
    assert len(ceiling_nodes) == 0, "Gabled roof should replace ceiling on top level"
    r = roof_nodes[0]
    assert r["roofType"] == "gabled"
    assert r["pitch"] == 35.0
    assert r["overhang"] == 0.6


def test_flat_roof_uses_ceiling_not_roof_node():
    """Techo plano no debe generar nodo tipo roof."""
    walls = [
        WallSegment(start=[-2, -2], end=[2, -2]),
        WallSegment(start=[2, -2], end=[2, 2]),
        WallSegment(start=[2, 2], end=[-2, 2]),
        WallSegment(start=[-2, 2], end=[-2, -2]),
    ]
    scene = _build_pascal_scene(walls, roof=RoofConfig(roof_type="flat"))
    nodes = scene["nodes"]
    assert not any(n["type"] == "roof" for n in nodes.values())
    assert any(n["type"] == "ceiling" for n in nodes.values())


# --- Mejora 5: Grosor y tipo de muro ---

def test_wall_thickness_and_type_preserved():
    """Grosor y tipo de muro deben conservarse en el nodo generado."""
    walls = [
        WallSegment(start=[0, 0], end=[4, 0], thickness=0.3, wall_type="exterior"),
        WallSegment(start=[4, 0], end=[4, 3], thickness=0.3, wall_type="exterior"),
        WallSegment(start=[4, 3], end=[0, 3], thickness=0.3, wall_type="exterior"),
        WallSegment(start=[0, 3], end=[0, 0], thickness=0.3, wall_type="exterior"),
        WallSegment(start=[2, 0], end=[2, 3], thickness=0.1, wall_type="interior"),
    ]
    scene = _build_pascal_scene(walls)
    nodes = scene["nodes"]
    wall_nodes = [n for n in nodes.values() if n["type"] == "wall"]
    exterior = [w for w in wall_nodes if w["frontSide"] == "exterior"]
    interior = [w for w in wall_nodes if w["frontSide"] == "interior"]
    assert len(exterior) == 4
    assert len(interior) == 1
    assert exterior[0]["thickness"] == 0.3
    assert interior[0]["thickness"] == 0.1


# --- Mejora 6: Mobiliario ---

def test_furniture_nodes_created():
    """Muebles deben aparecer como nodos tipo object en el nivel correcto."""
    walls = [
        WallSegment(start=[0, 0], end=[4, 0]),
        WallSegment(start=[4, 0], end=[4, 4]),
        WallSegment(start=[4, 4], end=[0, 4]),
        WallSegment(start=[0, 4], end=[0, 0]),
    ]
    items = [
        FurnitureItem(name="bed", position=[1.0, 1.0], rotation=90.0, level=0),
        FurnitureItem(name="desk", position=[3.0, 3.0], rotation=0.0, level=0),
    ]
    scene = _build_pascal_scene(walls, furniture=items)
    _assert_pascal_shape(scene)
    nodes = scene["nodes"]

    obj_nodes = [n for n in nodes.values() if n["type"] == "object"]
    assert len(obj_nodes) == 2
    names = {n["name"] for n in obj_nodes}
    assert names == {"bed", "desk"}
    bed = next(n for n in obj_nodes if n["name"] == "bed")
    assert bed["rotation"] == [0, 0, 90.0]
    assert bed["position"] == [1.0, 1.0, 0]


# --- Mejora 4: Validación geométrica ---

def test_validation_clips_door_position_out_of_range():
    """Posición de puerta fuera de [0.05, 0.95] debe ajustarse."""
    walls = [WallSegment(start=[0, 0], end=[5, 0])]
    extraction = ArchitectExtraction(
        walls=walls,
        doors=[DoorOpening(wall_index=0, position_along_wall=0.0, width=0.9, height=2.1)],
    )
    fixed = _validate_and_fix_extraction(extraction)
    assert fixed.doors[0].position_along_wall == 0.05


def test_validation_clips_wall_index_out_of_range():
    """wall_index mayor que len(walls) debe ajustarse al último muro."""
    walls = [WallSegment(start=[0, 0], end=[5, 0])]
    extraction = ArchitectExtraction(
        walls=walls,
        windows=[WindowOpening(wall_index=99, position_along_wall=0.5)],
    )
    fixed = _validate_and_fix_extraction(extraction)
    assert fixed.windows[0].wall_index == 0


def test_validation_clips_door_wider_than_wall():
    """Puerta más ancha que el muro (80%) debe recortarse."""
    walls = [WallSegment(start=[0, 0], end=[1.0, 0])]  # muro de 1m
    extraction = ArchitectExtraction(
        walls=walls,
        doors=[DoorOpening(wall_index=0, position_along_wall=0.5, width=5.0, height=2.1)],
    )
    fixed = _validate_and_fix_extraction(extraction)
    assert fixed.doors[0].width <= 0.8


def test_validation_fixes_stair_levels():
    """Escalera con to_level > num_levels debe corregirse."""
    walls = [
        WallSegment(start=[0, 0], end=[4, 0]), WallSegment(start=[4, 0], end=[4, 4]),
        WallSegment(start=[4, 4], end=[0, 4]), WallSegment(start=[0, 4], end=[0, 0]),
    ]
    extraction = ArchitectExtraction(
        walls=walls, num_levels=2,
        staircases=[StaircaseConfig(position=[1, 1], from_level=0, to_level=99)],
    )
    fixed = _validate_and_fix_extraction(extraction)
    assert fixed.staircases[0].to_level == 1  # capped at num_levels - 1


def test_validation_ensures_num_levels_at_least_1():
    """num_levels=0 debe corregirse a 1."""
    walls = [WallSegment(start=[0, 0], end=[4, 0])]
    extraction = ArchitectExtraction(walls=walls, num_levels=0)
    fixed = _validate_and_fix_extraction(extraction)
    assert fixed.num_levels == 1


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
        ("multi_level_scene", test_multi_level_scene),
        ("staircase_node_created", test_staircase_node_created),
        ("gabled_roof_node_on_top_level", test_gabled_roof_node_on_top_level),
        ("flat_roof_uses_ceiling_not_roof_node", test_flat_roof_uses_ceiling_not_roof_node),
        ("wall_thickness_and_type_preserved", test_wall_thickness_and_type_preserved),
        ("furniture_nodes_created", test_furniture_nodes_created),
        ("validation_clips_door_position_out_of_range", test_validation_clips_door_position_out_of_range),
        ("validation_clips_wall_index_out_of_range", test_validation_clips_wall_index_out_of_range),
        ("validation_clips_door_wider_than_wall", test_validation_clips_door_wider_than_wall),
        ("validation_fixes_stair_levels", test_validation_fixes_stair_levels),
        ("validation_ensures_num_levels_at_least_1", test_validation_ensures_num_levels_at_least_1),
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
