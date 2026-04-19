import pytest
from backend.core.engine import ExecutionEngine
from backend.core.state import WorkflowState
from backend.nodes.base import BaseNode
from backend.nodes.registry import node_registry
from backend.nodes.if_else_node import IfElseNode


class EchoNode(BaseNode):
    node_type = "echo"

    async def execute(self, state: WorkflowState, **kwargs) -> WorkflowState:
        output_key = self.config.get("output_key", "text")
        output_value = self.config.get("output_value", "echo")
        state.setdefault("node_outputs", {})
        state["node_outputs"][self.node_id] = {output_key: output_value}
        return state


# Register nodes for tests
for _cls in (IfElseNode, EchoNode):
    try:
        node_registry.register(_cls)
    except KeyError:
        pass


def _make_events():
    events = []

    async def on_event(event):
        events.append(event)

    return events, on_event


@pytest.mark.asyncio
async def test_engine_runs_linear_without_control_flow():
    """Regression: simple linear workflow without control flow still works."""
    graph_json = {
        "nodes": [
            {"id": "start_1", "type": "start", "data": {}},
            {"id": "echo_1", "type": "echo", "data": {"output_key": "text", "output_value": "hello"}},
            {"id": "end_1", "type": "end", "data": {}},
        ],
        "edges": [
            {"source": "start_1", "target": "echo_1"},
            {"source": "echo_1", "target": "end_1"},
        ],
    }
    engine = ExecutionEngine()
    events, on_event = _make_events()

    result = await engine.run(graph_json, user_input="test", on_event=on_event)

    assert result["node_outputs"]["echo_1"]["text"] == "hello"
    assert len([e for e in events if e["type"] == "node_end"]) == 3


@pytest.mark.asyncio
async def test_engine_runs_if_else_true_branch():
    graph_json = {
        "nodes": [
            {"id": "start_1", "type": "start", "data": {}},
            {
                "id": "if_1",
                "type": "if_else",
                "data": {
                    "branches": [
                        {
                            "id": "true",
                            "condition": {"left": "{{start_1.input}}", "op": "eq", "right": "test"},
                            "outputField": "echo_true.text",
                        },
                        {"id": "false", "condition": None},
                    ]
                },
            },
            {"id": "echo_true", "type": "echo", "data": {"parentId": "if_1", "branchId": "true", "output_key": "text", "output_value": "yes"}},
            {"id": "echo_false", "type": "echo", "data": {"parentId": "if_1", "branchId": "false", "output_key": "text", "output_value": "no"}},
            {"id": "end_1", "type": "end", "data": {}},
        ],
        "edges": [
            {"source": "start_1", "target": "if_1"},
            {"source": "if_1", "target": "end_1"},
        ],
    }
    engine = ExecutionEngine()
    events, on_event = _make_events()

    result = await engine.run(graph_json, user_input="test", on_event=on_event)

    assert result["node_outputs"]["if_1"]["branchTaken"] == "true"
    assert result["node_outputs"]["if_1"]["result"] == "yes"
    # Branch-internal node outputs do NOT leak to parent scope (per spec §3.1)
    assert "echo_true" not in result["node_outputs"]
    assert "echo_false" not in result["node_outputs"]

    branch_events = [e for e in events if e["type"] == "branch_taken"]
    assert len(branch_events) == 1
    assert branch_events[0]["branch_id"] == "true"
    assert branch_events[0]["condition_result"] is True


@pytest.mark.asyncio
async def test_engine_runs_if_else_false_branch():
    graph_json = {
        "nodes": [
            {"id": "start_1", "type": "start", "data": {}},
            {
                "id": "if_1",
                "type": "if_else",
                "data": {
                    "branches": [
                        {
                            "id": "true",
                            "condition": {"left": "{{start_1.input}}", "op": "eq", "right": "nope"},
                            "outputField": "echo_true.text",
                        },
                        {"id": "false", "condition": None, "outputField": "echo_false.text"},
                    ]
                },
            },
            {"id": "echo_true", "type": "echo", "data": {"parentId": "if_1", "branchId": "true", "output_key": "text", "output_value": "yes"}},
            {"id": "echo_false", "type": "echo", "data": {"parentId": "if_1", "branchId": "false", "output_key": "text", "output_value": "no"}},
            {"id": "end_1", "type": "end", "data": {}},
        ],
        "edges": [
            {"source": "start_1", "target": "if_1"},
            {"source": "if_1", "target": "end_1"},
        ],
    }
    engine = ExecutionEngine()
    events, on_event = _make_events()

    result = await engine.run(graph_json, user_input="test", on_event=on_event)

    assert result["node_outputs"]["if_1"]["branchTaken"] == "false"
    assert result["node_outputs"]["if_1"]["result"] == "no"
    # Branch-internal node outputs do NOT leak to parent scope (per spec §3.1)
    assert "echo_true" not in result["node_outputs"]
    assert "echo_false" not in result["node_outputs"]

    branch_events = [e for e in events if e["type"] == "branch_taken"]
    assert branch_events[0]["branch_id"] == "false"
    assert branch_events[0]["condition_result"] is False


@pytest.mark.asyncio
async def test_engine_skips_unselected_branch_nodes():
    """Only nodes in the selected branch should emit node_start / node_end."""
    graph_json = {
        "nodes": [
            {"id": "start_1", "type": "start", "data": {}},
            {
                "id": "if_1",
                "type": "if_else",
                "data": {
                    "branches": [
                        {"id": "true", "condition": {"left": "{{start_1.input}}", "op": "eq", "right": "x"}},
                        {"id": "false", "condition": None},
                    ]
                },
            },
            {"id": "echo_true", "type": "echo", "data": {"parentId": "if_1", "branchId": "true", "output_key": "text", "output_value": "yes"}},
            {"id": "echo_false", "type": "echo", "data": {"parentId": "if_1", "branchId": "false", "output_key": "text", "output_value": "no"}},
            {"id": "end_1", "type": "end", "data": {}},
        ],
        "edges": [
            {"source": "start_1", "target": "if_1"},
            {"source": "if_1", "target": "end_1"},
        ],
    }
    engine = ExecutionEngine()
    events, on_event = _make_events()

    await engine.run(graph_json, user_input="test", on_event=on_event)

    node_ids = [e.get("node_id") for e in events if e["type"] in ("node_start", "node_end")]
    assert "echo_true" not in node_ids
    assert "echo_false" in node_ids


@pytest.mark.asyncio
async def test_if_else_condition_operators():
    """Test all 8 condition operators."""
    from backend.nodes.if_else_node import IfElseNode

    state: WorkflowState = {
        "input": "",
        "inputs": {},
        "messages": [],
        "context": "",
        "llm_output": "",
        "audio_url": "",
        "node_outputs": {
            "n1": {"text": "hello world", "score": "42", "items": ["a", "b"], "meta": {"k": "v"}, "empty": "", "nullish": None},
        },
    }

    # eq
    assert IfElseNode.evaluate_condition({"left": "{{n1.text}}", "op": "eq", "right": "hello world"}, state) is True
    assert IfElseNode.evaluate_condition({"left": "{{n1.text}}", "op": "eq", "right": "nope"}, state) is False

    # ne
    assert IfElseNode.evaluate_condition({"left": "{{n1.text}}", "op": "ne", "right": "nope"}, state) is True
    assert IfElseNode.evaluate_condition({"left": "{{n1.text}}", "op": "ne", "right": "hello world"}, state) is False

    # contains (string)
    assert IfElseNode.evaluate_condition({"left": "{{n1.text}}", "op": "contains", "right": "world"}, state) is True
    assert IfElseNode.evaluate_condition({"left": "{{n1.text}}", "op": "contains", "right": "xyz"}, state) is False

    # contains (list)
    assert IfElseNode.evaluate_condition({"left": "{{n1.items}}", "op": "contains", "right": "a"}, state) is True
    assert IfElseNode.evaluate_condition({"left": "{{n1.items}}", "op": "contains", "right": "z"}, state) is False

    # contains (dict key)
    assert IfElseNode.evaluate_condition({"left": "{{n1.meta}}", "op": "contains", "right": "k"}, state) is True
    assert IfElseNode.evaluate_condition({"left": "{{n1.meta}}", "op": "contains", "right": "z"}, state) is False

    # not_contains
    assert IfElseNode.evaluate_condition({"left": "{{n1.text}}", "op": "not_contains", "right": "xyz"}, state) is True
    assert IfElseNode.evaluate_condition({"left": "{{n1.text}}", "op": "not_contains", "right": "world"}, state) is False

    # gt
    assert IfElseNode.evaluate_condition({"left": "{{n1.score}}", "op": "gt", "right": "40"}, state) is True
    assert IfElseNode.evaluate_condition({"left": "{{n1.score}}", "op": "gt", "right": "42"}, state) is False

    # lt
    assert IfElseNode.evaluate_condition({"left": "{{n1.score}}", "op": "lt", "right": "50"}, state) is True
    assert IfElseNode.evaluate_condition({"left": "{{n1.score}}", "op": "lt", "right": "42"}, state) is False

    # is_empty
    assert IfElseNode.evaluate_condition({"left": "{{n1.empty}}", "op": "is_empty"}, state) is True
    assert IfElseNode.evaluate_condition({"left": "{{n1.text}}", "op": "is_empty"}, state) is False
    assert IfElseNode.evaluate_condition({"left": "{{n1.nullish}}", "op": "is_empty"}, state) is True

    # is_not_empty
    assert IfElseNode.evaluate_condition({"left": "{{n1.text}}", "op": "is_not_empty"}, state) is True
    assert IfElseNode.evaluate_condition({"left": "{{n1.empty}}", "op": "is_not_empty"}, state) is False
    assert IfElseNode.evaluate_condition({"left": "{{n1.nullish}}", "op": "is_not_empty"}, state) is False
