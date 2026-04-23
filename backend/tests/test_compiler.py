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


def test_compiler_compile_returns_compiled_workflow():
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
    assert compiled is not None
    assert hasattr(compiled, "top_level_order")
    assert compiled.top_level_order == ["start_1", "end_1"]


def test_compiler_rejects_runtime_agent_node_type():
    graph_json = make_graph_json(
        nodes=[
            {"id": "start_1", "type": "start", "data": {}},
            {"id": "agent_1", "type": "agent", "data": {}},
            {"id": "end_1", "type": "end", "data": {}},
        ],
        edges=[
            {"source": "start_1", "target": "agent_1"},
            {"source": "agent_1", "target": "end_1"},
        ],
    )
    compiler = GraphCompiler()
    with pytest.raises(ValueError, match="Unknown node type: agent"):
        compiler.validate(graph_json)


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


def test_compiler_end_reference_missing_field_raises():
    graph_json = make_graph_json(
        nodes=[
            {"id": "start_1", "type": "start", "data": {}},
            {"id": "end_1", "type": "end", "data": {
                "outputs": [{"name": "url", "source": "reference", "value": "{{title}}"}]
            }},
        ],
        edges=[],
    )
    compiler = GraphCompiler()
    with pytest.raises(CompilerError, match="must specify a field name"):
        compiler.validate(graph_json)


def test_compiler_llm_missing_provider_id_raises():
    graph_json = make_graph_json(
        nodes=[
            {"id": "start_1", "type": "start", "data": {}},
            {"id": "llm_1", "type": "llm", "data": {}},
            {"id": "end_1", "type": "end", "data": {}},
        ],
        edges=[{"source": "start_1", "target": "llm_1"}, {"source": "llm_1", "target": "end_1"}],
    )
    compiler = GraphCompiler()
    from unittest.mock import MagicMock
    mock_db = MagicMock()
    with pytest.raises(CompilerError, match="must have a provider_id"):
        compiler.validate(graph_json, db=mock_db)


def test_compiler_llm_unknown_provider_id_raises():
    graph_json = make_graph_json(
        nodes=[
            {"id": "start_1", "type": "start", "data": {}},
            {"id": "llm_1", "type": "llm", "data": {"provider_id": 999}},
            {"id": "end_1", "type": "end", "data": {}},
        ],
        edges=[{"source": "start_1", "target": "llm_1"}, {"source": "llm_1", "target": "end_1"}],
    )
    compiler = GraphCompiler()
    from unittest.mock import MagicMock
    mock_db = MagicMock()
    mock_query = mock_db.query.return_value
    mock_query.filter.return_value.first.return_value = None
    with pytest.raises(CompilerError, match="references unknown provider"):
        compiler.validate(graph_json, db=mock_db)


def test_compiler_llm_disabled_provider_id_raises():
    graph_json = make_graph_json(
        nodes=[
            {"id": "start_1", "type": "start", "data": {}},
            {"id": "llm_1", "type": "llm", "data": {"provider_id": 1}},
            {"id": "end_1", "type": "end", "data": {}},
        ],
        edges=[{"source": "start_1", "target": "llm_1"}, {"source": "llm_1", "target": "end_1"}],
    )
    compiler = GraphCompiler()
    from unittest.mock import MagicMock
    mock_row = MagicMock()
    mock_row.enabled = False
    mock_db = MagicMock()
    mock_db.query.return_value.filter.return_value.first.return_value = mock_row
    with pytest.raises(CompilerError, match="references disabled provider"):
        compiler.validate(graph_json, db=mock_db)


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


def test_compiler_topological_sort_ignores_unconnected_nodes():
    graph_json = make_graph_json(
        nodes=[
            {"id": "start_1", "type": "start", "data": {}},
            {"id": "llm_1", "type": "llm", "data": {}},
            {"id": "tts_1", "type": "tts", "data": {}},
            {"id": "end_1", "type": "end", "data": {}},
            {"id": "orphan_1", "type": "llm", "data": {}},
        ],
        edges=[
            {"source": "start_1", "target": "llm_1"},
            {"source": "llm_1", "target": "end_1"},
        ],
    )
    compiler = GraphCompiler()
    order = compiler.topological_sort(graph_json)
    assert "orphan_1" not in order
    assert "tts_1" not in order
    assert order == ["start_1", "llm_1", "end_1"]


def test_compiler_preserves_v2_node_config():
    graph = {
        "version": 2,
        "nodes": [
            {"id": "start_1", "type": "start", "config": {"inputs": []}},
            {"id": "llm_1", "type": "llm", "config": {"provider_id": 1, "model": "gpt-4o"}},
            {
                "id": "end_1",
                "type": "end",
                "config": {
                    "outputs": [{"name": "answer", "source": "reference", "value": "{{llm_1.text}}"}],
                    "answer": "{{answer}}",
                },
            },
        ],
        "edges": [
            {"source": "start_1", "target": "llm_1"},
            {"source": "llm_1", "target": "end_1"},
        ],
    }

    compiled = GraphCompiler().compile(graph)

    assert compiled.nodes["llm_1"].config["provider_id"] == 1
    assert compiled.nodes["llm_1"].config["model"] == "gpt-4o"
    assert compiled.nodes["end_1"].config["outputs"][0]["value"] == "{{llm_1.text}}"


def test_compiler_uses_v2_parent_and_branch_fields():
    graph = {
        "version": 2,
        "nodes": [
            {"id": "start_1", "type": "start", "config": {}},
            {"id": "if_1", "type": "if_else", "config": {"branches": [{"id": "true", "condition": None}]}},
            {"id": "child_1", "type": "llm", "parentId": "if_1", "branchId": "true", "config": {"provider_id": 1}},
            {"id": "end_1", "type": "end", "config": {}},
        ],
        "edges": [
            {"source": "start_1", "target": "if_1"},
            {"source": "if_1", "target": "end_1"},
        ],
    }

    compiled = GraphCompiler().compile(graph)

    assert compiled.children_by_parent["if_1"] == ["child_1"]
    assert compiled.node_defs["child_1"]["branchId"] == "true"
