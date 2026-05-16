"""Verifica que architect_node produce JSON compatible con Pascal Editor useScene store."""
import json
import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from langchain_core.runnables import RunnableLambda

from api.paperclip_agents import (
    architect_node,
    _build_pascal_scene,
    _default_room_scene,
    WallSegment,
    ArchitectExtraction,
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


if __name__ == "__main__":
    tests = [
        ("happy_path_with_llm_extraction", test_happy_path_with_llm_extraction),
        ("fallback_when_llm_fails", test_fallback_when_llm_fails),
        ("default_room_directly", test_default_room_directly),
        ("build_scene_minimal", test_build_scene_minimal),
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
