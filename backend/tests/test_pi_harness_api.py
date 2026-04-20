from __future__ import annotations

import json

import pytest
from fastapi.testclient import TestClient
from langchain_core.language_models.fake_chat_models import FakeMessagesListChatModel
from langchain_core.messages import AIMessage
from sqlalchemy.orm import Session

from backend.models.provider import Provider
from backend.models.workflow import Workflow

API_PREFIXES = ["/api/pi_harness", "/api/harness"]


class ToolCallingFakeModel(FakeMessagesListChatModel):
    def bind_tools(self, tools, **kwargs):
        return self


def _parse_sse_events(text: str) -> list[dict]:
    events: list[dict] = []
    for block in text.strip().split("\n\n"):
        if not block.strip():
            continue

        event_type = ""
        data_lines: list[str] = []
        for line in block.splitlines():
            if line.startswith("event:"):
                event_type = line.removeprefix("event:").strip()
            elif line.startswith("data:"):
                data_lines.append(line.removeprefix("data:").strip())

        if not data_lines:
            continue

        payload = json.loads("\n".join(data_lines))
        payload.setdefault("type", event_type)
        events.append(payload)

    return events


def _ready_workflow_responses() -> list[AIMessage]:
    return [
        AIMessage(
            content="",
            tool_calls=[
                {
                    "id": "call_start",
                    "name": "add_node",
                    "args": {
                        "node_type": "start",
                        "node_id": "start",
                        "node_config": {
                            "inputs": [
                                {"name": "question", "type": "string", "required": True}
                            ]
                        },
                    },
                }
            ],
        ),
        AIMessage(
            content="",
            tool_calls=[
                {
                    "id": "call_llm",
                    "name": "add_node",
                    "args": {
                        "node_type": "llm",
                        "node_id": "llm_1",
                        "node_config": {"provider_id": 1, "model": "gpt-4o-mini"},
                    },
                }
            ],
        ),
        AIMessage(
            content="",
            tool_calls=[
                {
                    "id": "call_end",
                    "name": "add_node",
                    "args": {
                        "node_type": "end",
                        "node_id": "end",
                        "node_config": {
                            "outputs": [
                                {
                                    "name": "answer",
                                    "source": "reference",
                                    "value": "{{llm_1.text}}",
                                }
                            ]
                        },
                    },
                }
            ],
        ),
        AIMessage(
            content="",
            tool_calls=[
                {
                    "id": "call_edge_1",
                    "name": "connect_nodes",
                    "args": {"from_id": "start", "to_id": "llm_1"},
                }
            ],
        ),
        AIMessage(
            content="",
            tool_calls=[
                {
                    "id": "call_edge_2",
                    "name": "connect_nodes",
                    "args": {"from_id": "llm_1", "to_id": "end"},
                }
            ],
        ),
        AIMessage(
            content="",
            tool_calls=[
                {
                    "id": "call_finalize",
                    "name": "finalize_draft",
                    "args": {},
                }
            ],
        ),
        AIMessage(content="workflow ready"),
    ]


def _clarification_then_ready_responses() -> tuple[list[AIMessage], list[AIMessage]]:
    first_run = [
        AIMessage(
            content="",
            tool_calls=[
                {
                    "id": "call_clarify",
                    "name": "ask_clarification",
                    "args": {
                        "question": "Which output format do you want?",
                        "type": "approach_choice",
                        "options": ["text", "audio"],
                    },
                }
            ],
        )
    ]
    second_run = _ready_workflow_responses()
    return first_run, second_run


@pytest.mark.parametrize("base_path", API_PREFIXES)
def test_pi_harness_events_stream_to_ready(
    client: TestClient,
    db: Session,
    monkeypatch: pytest.MonkeyPatch,
    base_path: str,
):
    db.add(
        Provider(
            type="openai",
            name="PI Harness Provider",
            api_key_encrypted="enc",
            enabled=True,
            category="llm",
            selected_models=["gpt-4o-mini"],
        )
    )
    db.commit()

    model = ToolCallingFakeModel(responses=_ready_workflow_responses())
    monkeypatch.setattr(
        "backend.pi_harness.session.DBModelResolver.get_model",
        lambda self, *args, **kwargs: model,
    )

    created = client.post(f"{base_path}/sessions", json={"goal": "Build a workflow"})
    assert created.status_code == 200
    session_id = created.json()["session_id"]

    with client.stream("GET", f"{base_path}/sessions/{session_id}/events") as response:
        assert response.status_code == 200
        events = _parse_sse_events(response.read().decode())

    event_types = [event["type"] for event in events]
    assert "session_start" in event_types
    assert "tool_call" in event_types
    assert "graph_update" in event_types
    assert "harness_ready" in event_types
    assert events[-1]["type"] == "session_end"
    assert events[-1]["status"] == "ready"

    session_state = client.get(f"{base_path}/sessions/{session_id}")
    assert session_state.status_code == 200
    assert session_state.json()["status"] == "ready"
    assert len(session_state.json()["graph"]["nodes"]) == 3


@pytest.mark.parametrize("base_path", API_PREFIXES)
def test_pi_harness_clarify_resume_and_apply(
    client: TestClient,
    db: Session,
    monkeypatch: pytest.MonkeyPatch,
    base_path: str,
):
    db.add(
        Provider(
            type="openai",
            name="PI Harness Resume Provider",
            api_key_encrypted="enc",
            enabled=True,
            category="llm",
            selected_models=["gpt-4o-mini"],
        )
    )
    db.commit()

    first_run, second_run = _clarification_then_ready_responses()
    models = [
        ToolCallingFakeModel(responses=first_run),
        ToolCallingFakeModel(responses=second_run),
    ]

    def pop_model(self, *args, **kwargs):
        return models.pop(0)

    monkeypatch.setattr(
        "backend.pi_harness.session.DBModelResolver.get_model",
        pop_model,
    )

    created = client.post(f"{base_path}/sessions", json={"goal": "Need a workflow"})
    assert created.status_code == 200
    session_id = created.json()["session_id"]

    with client.stream("GET", f"{base_path}/sessions/{session_id}/events") as response:
        events = _parse_sse_events(response.read().decode())

    clarify_event = next(event for event in events if event["type"] == "awaiting_user_input")
    assert clarify_event["prompt"] == "Which output format do you want?"

    resumed = client.post(
        f"{base_path}/sessions/{session_id}/resume",
        json={"question_id": clarify_event["question_id"], "answer": "text"},
    )
    assert resumed.status_code == 200

    with client.stream("GET", f"{base_path}/sessions/{session_id}/events") as response:
        resumed_events = _parse_sse_events(response.read().decode())

    assert any(event["type"] == "harness_ready" for event in resumed_events)

    applied = client.post(f"{base_path}/sessions/{session_id}/apply")
    assert applied.status_code == 200
    workflow_id = applied.json()["workflow_id"]

    workflow = db.query(Workflow).filter(Workflow.id == workflow_id).first()
    assert workflow is not None
    assert len(workflow.graph["nodes"]) == 3


@pytest.mark.parametrize("base_path", API_PREFIXES)
def test_pi_harness_get_session_exposes_restore_state(
    client: TestClient,
    db: Session,
    monkeypatch: pytest.MonkeyPatch,
    base_path: str,
):
    db.add(
        Provider(
            type="openai",
            name="PI Harness Restore Provider",
            api_key_encrypted="enc",
            enabled=True,
            category="llm",
            selected_models=["gpt-4o-mini"],
        )
    )
    db.commit()

    first_run, second_run = _clarification_then_ready_responses()
    models = [
        ToolCallingFakeModel(responses=first_run),
        ToolCallingFakeModel(responses=second_run),
    ]

    monkeypatch.setattr(
        "backend.pi_harness.session.DBModelResolver.get_model",
        lambda self, *args, **kwargs: models.pop(0),
    )

    created = client.post(f"{base_path}/sessions", json={"goal": "Restore this workflow"})
    assert created.status_code == 200
    session_id = created.json()["session_id"]

    with client.stream("GET", f"{base_path}/sessions/{session_id}/events") as response:
        paused_events = _parse_sse_events(response.read().decode())

    paused_question = next(
        event for event in paused_events if event["type"] == "awaiting_user_input"
    )

    paused_session = client.get(f"{base_path}/sessions/{session_id}")
    assert paused_session.status_code == 200
    assert paused_session.json()["status"] == "awaiting_user"
    assert paused_session.json()["open_question"] == {
        "question_id": paused_question["question_id"],
        "prompt": "Which output format do you want?",
        "options": ["text", "audio"],
    }
    assert paused_session.json()["events"][-1]["type"] == "awaiting_user_input"

    resumed = client.post(
        f"{base_path}/sessions/{session_id}/resume",
        json={"question_id": paused_question["question_id"], "answer": "text"},
    )
    assert resumed.status_code == 200

    with client.stream("GET", f"{base_path}/sessions/{session_id}/events") as response:
        resumed_events = _parse_sse_events(response.read().decode())

    assert any(event["type"] == "harness_ready" for event in resumed_events)

    applied = client.post(f"{base_path}/sessions/{session_id}/apply")
    assert applied.status_code == 200
    workflow_id = applied.json()["workflow_id"]

    restored_session = client.get(f"{base_path}/sessions/{session_id}")
    assert restored_session.status_code == 200
    assert restored_session.json()["status"] == "applied"
    assert restored_session.json()["workflow_id"] == workflow_id
    assert restored_session.json()["open_question"] is None
    event_types = [event["type"] for event in restored_session.json()["events"]]
    assert "user_resumed" in event_types
    assert restored_session.json()["events"][-1]["type"] == "session_end"
    assert restored_session.json()["events"][-1]["status"] == "ready"


@pytest.mark.parametrize("base_path", API_PREFIXES)
def test_pi_harness_abort_session(
    client: TestClient,
    base_path: str,
):
    created = client.post(f"{base_path}/sessions", json={"goal": "Abort this workflow"})
    assert created.status_code == 200

    session_id = created.json()["session_id"]
    aborted = client.post(f"{base_path}/sessions/{session_id}/abort")
    assert aborted.status_code == 200
    assert aborted.json() == {"status": "aborted", "session_id": session_id}

    session_state = client.get(f"{base_path}/sessions/{session_id}")
    assert session_state.status_code == 200
    assert session_state.json()["status"] == "failed"
