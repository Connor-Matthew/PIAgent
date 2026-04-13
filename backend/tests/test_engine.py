import pytest
from backend.core.engine import ExecutionEngine
from backend.core.state import WorkflowState
from backend.nodes.base import BaseNode


@pytest.mark.asyncio
async def test_engine_executes_simple_workflow():
    graph_json = {
        "nodes": [
            {"id": "start_1", "type": "start", "data": {}},
            {"id": "end_1", "type": "end", "data": {}},
        ],
        "edges": [
            {"source": "start_1", "target": "end_1"},
        ],
    }

    events = []
    async def on_event(event):
        events.append(event)

    engine = ExecutionEngine()
    result = await engine.run(graph_json, user_input="hello", on_event=on_event)

    assert result["input"] == "hello"

    # Event count: 2 node_start + 2 node_end + 1 workflow_start + 1 workflow_end = 6
    assert len(events) == 6

    event_types = [e["type"] for e in events]
    assert event_types == [
        "workflow_start",
        "node_start",
        "node_end",
        "node_start",
        "node_end",
        "workflow_end",
    ]

    # Event ordering: node_start for a node must come before node_end for the same node
    for node_id in ["start_1", "end_1"]:
        start_indices = [i for i, e in enumerate(events) if e["type"] == "node_start" and e.get("node_id") == node_id]
        end_indices = [i for i, e in enumerate(events) if e["type"] == "node_end" and e.get("node_id") == node_id]
        assert len(start_indices) == 1
        assert len(end_indices) == 1
        assert start_indices[0] < end_indices[0]

    # Payload shape for node_end events
    node_end_events = [e for e in events if e["type"] == "node_end"]
    for e in node_end_events:
        assert "duration" in e
        assert "node_id" in e
        assert "output" in e


@pytest.mark.asyncio
async def test_engine_runs_without_event_callback():
    graph_json = {
        "nodes": [
            {"id": "start_1", "type": "start", "data": {}},
            {"id": "end_1", "type": "end", "data": {}},
        ],
        "edges": [
            {"source": "start_1", "target": "end_1"},
        ],
    }

    engine = ExecutionEngine()
    result = await engine.run(graph_json, user_input="hello", on_event=None)

    assert result["input"] == "hello"
    assert result["node_outputs"]["start"]["input"] == "hello"


class ExplodingNode(BaseNode):
    node_type = "exploding"

    async def execute(self, state: WorkflowState, **kwargs) -> WorkflowState:
        raise RuntimeError("boom")


@pytest.mark.asyncio
async def test_engine_emits_failed_event_on_error():
    from backend.nodes.registry import node_registry

    # Register the fake node
    node_registry.register(ExplodingNode)
    try:
        graph_json = {
            "nodes": [
                {"id": "start_1", "type": "start", "data": {}},
                {"id": "boom_1", "type": "exploding", "data": {}},
            ],
            "edges": [
                {"source": "start_1", "target": "boom_1"},
            ],
        }

        events = []
        async def on_event(event):
            events.append(event)

        engine = ExecutionEngine()

        with pytest.raises(RuntimeError, match="boom"):
            await engine.run(graph_json, user_input="hello", on_event=on_event)

        # Verify failed events are emitted before the exception propagates
        node_end_events = [e for e in events if e["type"] == "node_end"]
        failed_node_end = [e for e in node_end_events if e.get("status") == "failed"]
        assert len(failed_node_end) == 1
        assert failed_node_end[0]["node_id"] == "boom_1"
        assert failed_node_end[0]["error"] == "boom"

        workflow_end_events = [e for e in events if e["type"] == "workflow_end"]
        assert len(workflow_end_events) == 1
        assert workflow_end_events[0]["status"] == "failed"
    finally:
        node_registry.unregister("exploding")
