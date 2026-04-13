import pytest
from backend.core.engine import ExecutionEngine
from backend.core.state import WorkflowState


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
    # Should have node_start and node_end events
    event_types = [e["type"] for e in events]
    assert "node_start" in event_types
    assert "node_end" in event_types
    assert "workflow_end" in event_types
