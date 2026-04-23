from backend.models.assistant_session import AssistantSession
from backend.models.run_event import WorkflowRunEvent


def test_assistant_session_messages_roundtrip_string_workflow_id(db):
    session = AssistantSession(workflow_id="workflow-123")
    session.messages = [
        {"role": "user", "content": "这个工作流哪里有问题？"},
        {"role": "assistant", "content": "LLM 节点缺少 provider。"},
    ]

    db.add(session)
    db.commit()
    db.refresh(session)

    assert session.workflow_id == "workflow-123"
    assert session.messages == [
        {"role": "user", "content": "这个工作流哪里有问题？"},
        {"role": "assistant", "content": "LLM 节点缺少 provider。"},
    ]


def test_workflow_run_event_roundtrips_json_payload(db):
    row = WorkflowRunEvent(
        workflow_id="workflow-123",
        run_id="run-123",
        seq=2,
        event_type="node_end",
    )
    row.event = {
        "type": "node_end",
        "node_id": "llm_1",
        "output": {"text": "hello"},
    }

    db.add(row)
    db.commit()
    db.refresh(row)

    assert row.event == {
        "type": "node_end",
        "node_id": "llm_1",
        "output": {"text": "hello"},
    }
