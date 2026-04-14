import pytest
from backend.core.compiler import GraphCompiler, CycleDetectedError, CompilerError
from backend.nodes.base import BaseNode
from backend.nodes.registry import node_registry
from backend.core.state import WorkflowState


class MockLLMNode(BaseNode):
    node_type = "llm"

    async def execute(self, state: WorkflowState, **kwargs) -> WorkflowState:
        return state


class MockTTSNode(BaseNode):
    node_type = "tts"

    async def execute(self, state: WorkflowState, **kwargs) -> WorkflowState:
        return state


for _mock_cls in (MockLLMNode, MockTTSNode):
    try:
        node_registry.register(_mock_cls)
    except KeyError:
        pass


def make_graph_json(nodes, edges):
    return {"nodes": nodes, "edges": edges}


def test_compiler_detects_cycle():
    graph_json = make_graph_json(
        nodes=[
            {"id": "a", "type": "start", "data": {}},
            {"id": "b", "type": "llm", "data": {}},
            {"id": "c", "type": "end", "data": {}},
        ],
        edges=[
            {"source": "a", "target": "b"},
            {"source": "b", "target": "c"},
            {"source": "c", "target": "a"},
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
            {"id": "end_1", "type": "end", "data": {}},
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
    with pytest.raises(CompilerError, match="must contain exactly one start node"):
        compiler.compile(graph_json)


def test_compiler_dangling_source_reference_raises():
    graph_json = make_graph_json(
        nodes=[
            {"id": "start_1", "type": "start", "data": {}},
            {"id": "end_1", "type": "end", "data": {}},
        ],
        edges=[
            {"source": "missing_node", "target": "start_1"},
        ],
    )
    compiler = GraphCompiler()
    with pytest.raises(ValueError, match="undeclared source node"):
        compiler.validate(graph_json)


def test_compiler_missing_start_node_raises():
    graph_json = make_graph_json(
        nodes=[
            {"id": "end_1", "type": "end", "data": {}},
        ],
        edges=[],
    )
    compiler = GraphCompiler()
    with pytest.raises(CompilerError, match="must contain exactly one start node"):
        compiler.validate(graph_json)


def test_compiler_multiple_end_nodes_raises():
    graph_json = make_graph_json(
        nodes=[
            {"id": "start_1", "type": "start", "data": {}},
            {"id": "end_1", "type": "end", "data": {}},
            {"id": "end_2", "type": "end", "data": {}},
        ],
        edges=[],
    )
    compiler = GraphCompiler()
    with pytest.raises(CompilerError, match="must contain exactly one end node"):
        compiler.validate(graph_json)


def test_compiler_end_reference_invalid_format_raises():
    graph_json = make_graph_json(
        nodes=[
            {"id": "start_1", "type": "start", "data": {}},
            {"id": "end_1", "type": "end", "data": {
                "outputs": [{"name": "bad", "source": "reference", "value": "not-a-reference"}]
            }},
        ],
        edges=[],
    )
    compiler = GraphCompiler()
    with pytest.raises(CompilerError, match="must match"):
        compiler.validate(graph_json)


def test_compiler_end_reference_unknown_node_raises():
    graph_json = make_graph_json(
        nodes=[
            {"id": "start_1", "type": "start", "data": {}},
            {"id": "end_1", "type": "end", "data": {
                "outputs": [{"name": "url", "source": "reference", "value": "{{missing_node.audio_url}}"}]
            }},
        ],
        edges=[],
    )
    compiler = GraphCompiler()
    with pytest.raises(CompilerError, match="points to unknown node"):
        compiler.validate(graph_json)


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
