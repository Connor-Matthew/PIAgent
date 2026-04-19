import pytest
from backend.core.compiler import GraphCompiler, CycleDetectedError, CompilerError


def make_graph_json(nodes, edges):
    return {"nodes": nodes, "edges": edges}


def test_compiler_rejects_orphan_parent_id():
    graph_json = make_graph_json(
        nodes=[
            {"id": "start_1", "type": "start", "data": {}},
            {"id": "llm_1", "type": "llm", "data": {"parentId": "missing_parent"}},
            {"id": "end_1", "type": "end", "data": {}},
        ],
        edges=[
            {"source": "start_1", "target": "llm_1"},
            {"source": "llm_1", "target": "end_1"},
        ],
    )
    compiler = GraphCompiler()
    with pytest.raises(CompilerError, match="parentId.*does not exist"):
        compiler.validate(graph_json)


def test_compiler_rejects_cross_scope_edge():
    """External node must not connect directly to a child node."""
    graph_json = make_graph_json(
        nodes=[
            {"id": "start_1", "type": "start", "data": {}},
            {"id": "llm_1", "type": "llm", "data": {}},
            {"id": "llm_2", "type": "llm", "data": {"parentId": "llm_1"}},
            {"id": "end_1", "type": "end", "data": {}},
        ],
        edges=[
            {"source": "start_1", "target": "llm_1"},
            {"source": "llm_1", "target": "end_1"},
            {"source": "start_1", "target": "llm_2"},  # invalid: external -> child
        ],
    )
    compiler = GraphCompiler()
    with pytest.raises(CompilerError, match="Invalid cross-scope edge"):
        compiler.validate(graph_json)


def test_compiler_rejects_cycle_in_subgraph():
    graph_json = make_graph_json(
        nodes=[
            {"id": "start_1", "type": "start", "data": {}},
            {"id": "llm_1", "type": "llm", "data": {}},
            {"id": "llm_a", "type": "llm", "data": {"parentId": "llm_1"}},
            {"id": "llm_b", "type": "llm", "data": {"parentId": "llm_1"}},
            {"id": "end_1", "type": "end", "data": {}},
        ],
        edges=[
            {"source": "start_1", "target": "llm_1"},
            {"source": "llm_1", "target": "end_1"},
            {"source": "llm_a", "target": "llm_b"},
            {"source": "llm_b", "target": "llm_a"},  # cycle inside subgraph
        ],
    )
    compiler = GraphCompiler()
    with pytest.raises(CycleDetectedError, match="Subgraph.*contains a cycle"):
        compiler.validate(graph_json)


def test_compiler_accepts_nested_parent_id():
    """Parent -> child and child -> parent edges are allowed; siblings inside the same parent are allowed."""
    graph_json = make_graph_json(
        nodes=[
            {"id": "start_1", "type": "start", "data": {}},
            {"id": "llm_1", "type": "llm", "data": {}},
            {"id": "llm_a", "type": "llm", "data": {"parentId": "llm_1"}},
            {"id": "llm_b", "type": "llm", "data": {"parentId": "llm_1"}},
            {"id": "end_1", "type": "end", "data": {}},
        ],
        edges=[
            {"source": "start_1", "target": "llm_1"},
            {"source": "llm_1", "target": "llm_a"},   # parent -> child
            {"source": "llm_a", "target": "llm_b"},   # sibling -> sibling
            {"source": "llm_b", "target": "llm_1"},   # child -> parent
            {"source": "llm_1", "target": "end_1"},
        ],
    )
    compiler = GraphCompiler()
    compiler.validate(graph_json)  # should not raise


def test_compiler_rejects_start_with_parent_id():
    graph_json = make_graph_json(
        nodes=[
            {"id": "start_1", "type": "start", "data": {"parentId": "some_parent"}},
            {"id": "end_1", "type": "end", "data": {}},
        ],
        edges=[{"source": "start_1", "target": "end_1"}],
    )
    compiler = GraphCompiler()
    with pytest.raises(CompilerError, match="cannot have a parentId"):
        compiler.validate(graph_json)
