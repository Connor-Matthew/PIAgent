from types import SimpleNamespace

from backend.models.assistant_session import AssistantSession
from backend.models.workflow import Workflow


SAMPLE_GRAPH = {
    "nodes": [
        {"id": "start_1", "type": "start", "data": {}},
        {"id": "end_1", "type": "end", "data": {}},
    ],
    "edges": [
        {"source": "start_1", "target": "end_1"},
    ],
}


def _create_workflow(db):
    workflow = Workflow(name="Assistant Route Test")
    workflow.graph = SAMPLE_GRAPH
    db.add(workflow)
    db.commit()
    db.refresh(workflow)
    return workflow


def test_assistant_stream_returns_404_for_missing_workflow(client):
    resp = client.post(
        "/api/assistant/sessions/missing-workflow/stream",
        json={"message": "这个工作流有什么问题？"},
    )

    assert resp.status_code == 404


def test_assistant_stream_creates_one_session_and_translates_sse(client, db, monkeypatch):
    workflow = _create_workflow(db)

    class FakeAgent:
        async def astream(self, state, stream_mode):
            assert stream_mode == "messages"
            assert state["messages"][-1].content in {"这个工作流有什么问题？", "再看一次"}
            yield (
                SimpleNamespace(
                    type="ai",
                    content="",
                    tool_calls=[
                        {"id": "call_1", "name": "get_current_graph", "args": {}},
                    ],
                ),
                {},
            )
            yield (
                SimpleNamespace(
                    type="tool",
                    content='{"name": "Assistant Route Test"}',
                    name="get_current_graph",
                    tool_call_id="call_1",
                ),
                {},
            )
            yield (SimpleNamespace(type="ai", content="这个流程目前只有开始和结束节点。"), {})

    monkeypatch.setattr("backend.assistant.routes.build_assistant_agent", lambda db, workflow_id: FakeAgent())

    first_resp = client.post(
        f"/api/assistant/sessions/{workflow.id}/stream",
        json={"message": "这个工作流有什么问题？"},
    )
    second_resp = client.post(
        f"/api/assistant/sessions/{workflow.id}/stream",
        json={"message": "再看一次"},
    )

    assert first_resp.status_code == 200
    assert "event: session.started" in first_resp.text
    assert "event: tool.call" in first_resp.text
    assert "event: tool.result" in first_resp.text
    assert "event: message.delta" in first_resp.text
    assert "event: message.done" in first_resp.text
    assert "这个流程目前只有开始和结束节点。" in first_resp.text
    assert second_resp.status_code == 200

    sessions = db.query(AssistantSession).filter(AssistantSession.workflow_id == workflow.id).all()
    assert len(sessions) == 1
    assert sessions[0].messages[-2:] == [
        {"role": "user", "content": "再看一次"},
        {"role": "assistant", "content": "这个流程目前只有开始和结束节点。"},
    ]
