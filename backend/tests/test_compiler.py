import pytest
from backend.core.compiler import GraphCompiler, CycleDetectedError


def make_graph_json(nodes, edges):
    return {"nodes": nodes, "edges": edges}


def test_compiler_detects_cycle():
    graph_json = make_graph_json(
        nodes=[
            {"id": "a", "type": "start", "data": {}},
            {"id": "b", "type": "llm", "data": {}},
        ],
        edges=[
            {"source": "a", "target": "b"},
            {"source": "b", "target": "a"},
        ],
    )
    compiler = GraphCompiler()
    with pytest.raises(CycleDetectedError):
        compiler.validate(graph_json)


def test_compiler_topological_sort():
    graph_json = make_graph_json(
        nodes=[
            {"id": "start_1", "type": "start", "data": {}},
            {"id": "llm_1", "type": "llm", "data": {}},
            {"id": "tts_1", "type": "tts", "data": {}},
            {"id": "end_1", "type": "end", "data": {}},
        ],
        edges=[
            {"source": "start_1", "target": "llm_1"},
            {"source": "llm_1", "target": "tts_1"},
            {"source": "tts_1", "target": "end_1"},
        ],
    )
    compiler = GraphCompiler()
    order = compiler.topological_sort(graph_json)
    assert order == ["start_1", "llm_1", "tts_1", "end_1"]


def test_compiler_compile_returns_langgraph():
    graph_json = make_graph_json(
        nodes=[
            {"id": "start_1", "type": "start", "data": {}},
            {"id": "end_1", "type": "end", "data": {}},
        ],
        edges=[
            {"source": "start_1", "target": "end_1"},
        ],
    )
    compiler = GraphCompiler()
    compiled = compiler.compile(graph_json)
    # compiled should be a LangGraph CompiledGraph
    assert compiled is not None
    assert hasattr(compiled, "invoke")


def test_compiler_dangling_edge_reference_raises():
    graph_json = make_graph_json(
        nodes=[
            {"id": "start_1", "type": "start", "data": {}},
        ],
        edges=[
            {"source": "start_1", "target": "missing_node"},
        ],
    )
    compiler = GraphCompiler()
    with pytest.raises(ValueError, match="undeclared target node"):
        compiler.validate(graph_json)


def test_compiler_empty_graph_raises():
    graph_json = make_graph_json(nodes=[], edges=[])
    compiler = GraphCompiler()
    with pytest.raises(ValueError, match="Workflow graph has no nodes"):
        compiler.compile(graph_json)


def test_compiler_duplicate_node_ids_raises():
    graph_json = make_graph_json(
        nodes=[
            {"id": "node_1", "type": "start", "data": {}},
            {"id": "node_1", "type": "llm", "data": {}},
        ],
        edges=[],
    )
    compiler = GraphCompiler()
    with pytest.raises(ValueError, match="Duplicate node IDs"):
        compiler.validate(graph_json)
