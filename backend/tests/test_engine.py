import pytest
from unittest.mock import patch, AsyncMock, MagicMock

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

    # workflow_end should include answer and outputs
    workflow_end_events = [e for e in events if e["type"] == "workflow_end"]
    assert len(workflow_end_events) == 1
    assert "answer" in workflow_end_events[0]
    assert "outputs" in workflow_end_events[0]


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
    assert result["node_outputs"]["start_1"]["input"] == "hello"


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
                {"id": "end_1", "type": "end", "data": {}},  # Compiler requires exactly one end
                {"id": "boom_1", "type": "exploding", "data": {}},
            ],
            "edges": [
                {"source": "start_1", "target": "boom_1"},
                {"source": "boom_1", "target": "end_1"},
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


@pytest.mark.asyncio
async def test_engine_end_to_end_with_references():
    """Integration test: Start -> LLM -> TTS -> End with variable references."""
    graph_json = {
        "nodes": [
            {"id": "start_1", "type": "start", "data": {"inputs": [{"name": "topic", "type": "text", "required": True}]}},
            {"id": "llm_1", "type": "llm", "data": {}},
            {"id": "tts_1", "type": "tts", "data": {}},
            {"id": "end_1", "type": "end", "data": {
                "outputs": [
                    {"name": "audio_url", "source": "reference", "value": "{{tts_1.audio_url}}"},
                    {"name": "title", "source": "input", "value": "今天的 AI 播客"},
                ],
                "answer": "{{title}}: {{audio_url}}",
            }},
        ],
        "edges": [
            {"source": "start_1", "target": "llm_1"},
            {"source": "llm_1", "target": "tts_1"},
            {"source": "tts_1", "target": "end_1"},
        ],
    }

    with patch("backend.nodes.llm_node.LLMNode._get_chat_model") as mock_llm, \
         patch("backend.nodes.tts_node.TTSNode._get_tts_provider") as mock_tts:
        mock_model = AsyncMock()
        mock_response = MagicMock()
        mock_response.content = "Generated podcast script."
        mock_model.ainvoke.return_value = mock_response
        mock_llm.return_value = mock_model

        mock_provider = AsyncMock()
        mock_provider.synthesize.return_value = "/audio/test.mp3"
        mock_tts.return_value = mock_provider

        engine = ExecutionEngine()
        result = await engine.run(
            graph_json,
            inputs={"topic": "AI 教育"},
        )

        assert result["answer"] == "今天的 AI 播客: /audio/test.mp3"
        assert result["outputs"]["audio_url"] == "/audio/test.mp3"
        assert result["outputs"]["title"] == "今天的 AI 播客"
        assert result["node_outputs"]["llm_1"]["text"] == "Generated podcast script."
        assert result["node_outputs"]["tts_1"]["audio_url"] == "/audio/test.mp3"
