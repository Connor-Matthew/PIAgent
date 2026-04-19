import pytest
from backend.core.engine import ExecutionEngine
from backend.core.state import WorkflowState
from backend.nodes.base import BaseNode
from backend.nodes.registry import node_registry
from backend.nodes.if_else_node import IfElseNode
from backend.nodes.iteration_node import IterationNode


class TemplateEchoNode(BaseNode):
    node_type = "template_echo"

    async def execute(self, state: WorkflowState, **kwargs) -> WorkflowState:
        from backend.core.template import render_template

        output_key = self.config.get("output_key", "text")
        template = self.config.get("template", "")
        value = render_template(template, state)
        state.setdefault("node_outputs", {})
        state["node_outputs"][self.node_id] = {output_key: value}
        return state


# Register nodes for tests
for _cls in (IfElseNode, IterationNode, TemplateEchoNode):
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
async def test_engine_runs_iteration_serial():
    graph_json = {
        "nodes": [
            {"id": "start_1", "type": "start", "data": {}},
            {
                "id": "iter_1",
                "type": "iteration",
                "data": {
                    "inputRef": "{{start_1.items}}",
                    "outputField": "echo_1.text",
                },
            },
            {
                "id": "echo_1",
                "type": "template_echo",
                "data": {"parentId": "iter_1", "template": "got: {{item}}"},
            },
            {"id": "end_1", "type": "end", "data": {}},
        ],
        "edges": [
            {"source": "start_1", "target": "iter_1"},
            {"source": "iter_1", "target": "end_1"},
        ],
    }
    engine = ExecutionEngine()
    events, on_event = _make_events()

    result = await engine.run(
        graph_json,
        user_input="",
        inputs={"items": ["a", "b", "c"]},
        on_event=on_event,
    )

    assert result["node_outputs"]["iter_1"]["results"] == ["got: a", "got: b", "got: c"]
    assert result["node_outputs"]["iter_1"]["errors"] == []

    iter_item_starts = [e for e in events if e["type"] == "iteration_item_start"]
    assert len(iter_item_starts) == 3


@pytest.mark.asyncio
async def test_iteration_exposes_item_and_index_in_template():
    graph_json = {
        "nodes": [
            {"id": "start_1", "type": "start", "data": {}},
            {
                "id": "iter_1",
                "type": "iteration",
                "data": {
                    "inputRef": "{{start_1.items}}",
                    "itemVar": "item",
                    "indexVar": "idx",
                    "outputField": "echo_1.text",
                },
            },
            {
                "id": "echo_1",
                "type": "template_echo",
                "data": {"parentId": "iter_1", "template": "{{idx}}:{{item}}"},
            },
            {"id": "end_1", "type": "end", "data": {}},
        ],
        "edges": [
            {"source": "start_1", "target": "iter_1"},
            {"source": "iter_1", "target": "end_1"},
        ],
    }
    engine = ExecutionEngine()
    result = await engine.run(
        graph_json,
        user_input="",
        inputs={"items": ["x", "y"]},
    )

    assert result["node_outputs"]["iter_1"]["results"] == ["0:x", "1:y"]


@pytest.mark.asyncio
async def test_iteration_collects_results_in_order():
    """Even if body execution order varies, results must stay in input order."""
    graph_json = {
        "nodes": [
            {"id": "start_1", "type": "start", "data": {}},
            {
                "id": "iter_1",
                "type": "iteration",
                "data": {
                    "inputRef": "{{start_1.items}}",
                    "outputField": "echo_1.text",
                },
            },
            {
                "id": "echo_1",
                "type": "template_echo",
                "data": {"parentId": "iter_1", "template": "{{item}}"},
            },
            {"id": "end_1", "type": "end", "data": {}},
        ],
        "edges": [
            {"source": "start_1", "target": "iter_1"},
            {"source": "iter_1", "target": "end_1"},
        ],
    }
    engine = ExecutionEngine()
    result = await engine.run(
        graph_json,
        user_input="",
        inputs={"items": ["first", "second", "third"]},
    )

    assert result["node_outputs"]["iter_1"]["results"] == ["first", "second", "third"]


@pytest.mark.asyncio
async def test_iteration_empty_input_produces_empty_results():
    graph_json = {
        "nodes": [
            {"id": "start_1", "type": "start", "data": {}},
            {
                "id": "iter_1",
                "type": "iteration",
                "data": {
                    "inputRef": "{{start_1.items}}",
                    "outputField": "echo_1.text",
                },
            },
            {
                "id": "echo_1",
                "type": "template_echo",
                "data": {"parentId": "iter_1", "template": "{{item}}"},
            },
            {"id": "end_1", "type": "end", "data": {}},
        ],
        "edges": [
            {"source": "start_1", "target": "iter_1"},
            {"source": "iter_1", "target": "end_1"},
        ],
    }
    engine = ExecutionEngine()
    result = await engine.run(
        graph_json,
        user_input="",
        inputs={"items": []},
    )

    assert result["node_outputs"]["iter_1"]["results"] == []
    assert result["node_outputs"]["iter_1"]["errors"] == []
