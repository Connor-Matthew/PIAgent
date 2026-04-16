from backend.models.knowledge_base import KnowledgeBase
from backend.models.workflow import Workflow


def test_create_agent_session_requires_llm_provider(client):
    resp = client.post("/api/agent/sessions", json={"goal": "做一期播客"})
    assert resp.status_code == 400
    assert "LLM provider" in resp.json()["detail"]


def test_create_agent_session_returns_default_draft(client):
    provider_resp = client.post(
        "/api/providers",
        json={
            "type": "openai",
            "name": "Planner OpenAI",
            "api_key": "sk-test",
        },
    )
    assert provider_resp.status_code == 201

    session_resp = client.post(
        "/api/agent/sessions",
        json={"goal": "给我一份注意力机制讲稿，不需要音频"},
    )
    assert session_resp.status_code == 201
    session_id = session_resp.json()["session_id"]

    get_resp = client.get(f"/api/agent/sessions/{session_id}")
    assert get_resp.status_code == 200
    data = get_resp.json()
    assert data["status"] == "ready"
    assert data["recipe_ir"]["recipe"] == "start_llm_end"
    assert [node["type"] for node in data["generated_graph"]["nodes"]] == [
        "start",
        "llm",
        "end",
    ]


def test_create_agent_session_prefers_rag_and_tts_when_available(client, db):
    provider_resp = client.post(
        "/api/providers",
        json={
            "type": "openai",
            "name": "Planner OpenAI",
            "api_key": "sk-test",
        },
    )
    assert provider_resp.status_code == 201
    tts_resp = client.post(
        "/api/providers",
        json={
            "type": "minimax_tts",
            "category": "tts",
            "name": "Planner MiniMax",
            "api_key": "sk-test",
        },
    )
    assert tts_resp.status_code == 201
    db.add(KnowledgeBase(name="Transformer 知识库", description="docs"))
    db.commit()

    session_resp = client.post(
        "/api/agent/sessions",
        json={"goal": "做一期面向本科生的 Transformer 科普播客，引用知识库资料"},
    )
    assert session_resp.status_code == 201

    session_id = session_resp.json()["session_id"]
    data = client.get(f"/api/agent/sessions/{session_id}").json()
    assert data["recipe_ir"]["recipe"] == "start_rag_llm_tts_end"
    assert [node["type"] for node in data["generated_graph"]["nodes"]] == [
        "start",
        "rag",
        "llm",
        "tts",
        "end",
    ]


def test_create_agent_session_can_enter_clarifying_state(client, db):
    provider_resp = client.post(
        "/api/providers",
        json={
            "type": "openai",
            "name": "Planner OpenAI",
            "api_key": "sk-test",
        },
    )
    assert provider_resp.status_code == 201
    tts_resp = client.post(
        "/api/providers",
        json={
            "type": "minimax_tts",
            "category": "tts",
            "name": "Planner MiniMax",
            "api_key": "sk-test",
        },
    )
    assert tts_resp.status_code == 201

    session_resp = client.post(
        "/api/agent/sessions",
        json={"goal": "给我整理一份 Transformer 内容"},
    )
    assert session_resp.status_code == 201

    session_id = session_resp.json()["session_id"]
    data = client.get(f"/api/agent/sessions/{session_id}").json()
    assert data["status"] == "clarifying"
    assert data["clarification_turns"][0]["dim"] == "need_audio_output"


def test_answer_agent_session_advances_to_next_question(client, db):
    provider_resp = client.post(
        "/api/providers",
        json={
            "type": "openai",
            "name": "Planner OpenAI",
            "api_key": "sk-test",
        },
    )
    assert provider_resp.status_code == 201
    tts_resp = client.post(
        "/api/providers",
        json={
            "type": "minimax_tts",
            "category": "tts",
            "name": "Planner MiniMax",
            "api_key": "sk-test",
        },
    )
    assert tts_resp.status_code == 201
    db.add(KnowledgeBase(name="Transformer 知识库", description="docs"))
    db.commit()

    session_id = client.post(
        "/api/agent/sessions",
        json={"goal": "给我整理一份 Transformer 内容"},
    ).json()["session_id"]

    answer_resp = client.post(
        f"/api/agent/sessions/{session_id}/answer",
        json={"answer": "需要音频"},
    )
    assert answer_resp.status_code == 202

    data = client.get(f"/api/agent/sessions/{session_id}").json()
    assert data["status"] == "clarifying"
    assert data["answered_dims"]["need_audio_output"] is True
    assert data["clarification_turns"][-1]["dim"] == "use_knowledge_base"


def test_answer_agent_session_can_finalize_plan(client, db):
    provider_resp = client.post(
        "/api/providers",
        json={
            "type": "openai",
            "name": "Planner OpenAI",
            "api_key": "sk-test",
        },
    )
    assert provider_resp.status_code == 201
    tts_resp = client.post(
        "/api/providers",
        json={
            "type": "minimax_tts",
            "category": "tts",
            "name": "Planner MiniMax",
            "api_key": "sk-test",
        },
    )
    assert tts_resp.status_code == 201
    db.add(KnowledgeBase(name="Transformer 知识库", description="docs"))
    db.commit()

    session_id = client.post(
        "/api/agent/sessions",
        json={"goal": "给我整理一份 Transformer 内容"},
    ).json()["session_id"]

    client.post(
        f"/api/agent/sessions/{session_id}/answer",
        json={"answer": "需要音频"},
    )
    final_resp = client.post(
        f"/api/agent/sessions/{session_id}/answer",
        json={"answer": "不用知识库"},
    )
    assert final_resp.status_code == 202

    data = client.get(f"/api/agent/sessions/{session_id}").json()
    assert data["status"] == "ready"
    assert data["recipe_ir"]["recipe"] == "start_llm_tts_end"


def test_skip_agent_session_builds_default_plan(client, db):
    provider_resp = client.post(
        "/api/providers",
        json={
            "type": "openai",
            "name": "Planner OpenAI",
            "api_key": "sk-test",
        },
    )
    assert provider_resp.status_code == 201
    tts_resp = client.post(
        "/api/providers",
        json={
            "type": "minimax_tts",
            "category": "tts",
            "name": "Planner MiniMax",
            "api_key": "sk-test",
        },
    )
    assert tts_resp.status_code == 201

    session_id = client.post(
        "/api/agent/sessions",
        json={"goal": "给我整理一份 Transformer 内容"},
    ).json()["session_id"]

    skip_resp = client.post(f"/api/agent/sessions/{session_id}/skip")
    assert skip_resp.status_code == 202

    data = client.get(f"/api/agent/sessions/{session_id}").json()
    assert data["status"] == "ready"
    assert data["recipe_ir"]["recipe"] == "start_llm_tts_end"


def test_agent_session_events_replay_history(client, db):
    provider_resp = client.post(
        "/api/providers",
        json={
            "type": "openai",
            "name": "Planner OpenAI",
            "api_key": "sk-test",
        },
    )
    assert provider_resp.status_code == 201
    tts_resp = client.post(
        "/api/providers",
        json={
            "type": "minimax_tts",
            "category": "tts",
            "name": "Planner MiniMax",
            "api_key": "sk-test",
        },
    )
    assert tts_resp.status_code == 201

    session_id = client.post(
        "/api/agent/sessions",
        json={"goal": "给我整理一份 Transformer 内容"},
    ).json()["session_id"]

    events_resp = client.get(f"/api/agent/sessions/{session_id}/events?replay_only=true")
    assert events_resp.status_code == 200
    assert events_resp.headers.get("content-type") == "text/event-stream; charset=utf-8"
    assert "event: agent_session_started" in events_resp.text
    assert "event: clarify_question" in events_resp.text


def test_answer_agent_session_deadlock_uses_default_path(client, db):
    provider_resp = client.post(
        "/api/providers",
        json={
            "type": "openai",
            "name": "Planner OpenAI",
            "api_key": "sk-test",
        },
    )
    assert provider_resp.status_code == 201
    tts_resp = client.post(
        "/api/providers",
        json={
            "type": "minimax_tts",
            "category": "tts",
            "name": "Planner MiniMax",
            "api_key": "sk-test",
        },
    )
    assert tts_resp.status_code == 201

    session_id = client.post(
        "/api/agent/sessions",
        json={"goal": "给我整理一份 Transformer 内容"},
    ).json()["session_id"]

    first_resp = client.post(
        f"/api/agent/sessions/{session_id}/answer",
        json={"answer": "以后再聊"},
    )
    assert first_resp.status_code == 202

    second_resp = client.post(
        f"/api/agent/sessions/{session_id}/answer",
        json={"answer": "回头再看"},
    )
    assert second_resp.status_code == 202

    session_data = client.get(f"/api/agent/sessions/{session_id}").json()
    assert session_data["status"] == "ready"

    events_resp = client.get(f"/api/agent/sessions/{session_id}/events?replay_only=true")
    assert "clarification_deadlock" in events_resp.text


def test_apply_agent_session_creates_workflow(client):
    provider_resp = client.post(
        "/api/providers",
        json={
            "type": "openai",
            "name": "Planner OpenAI",
            "api_key": "sk-test",
        },
    )
    assert provider_resp.status_code == 201

    session_resp = client.post(
        "/api/agent/sessions",
        json={"goal": "给我一份注意力机制讲稿，不需要音频"},
    )
    session_id = session_resp.json()["session_id"]

    apply_resp = client.post(f"/api/agent/sessions/{session_id}/apply")
    assert apply_resp.status_code == 200
    workflow_id = apply_resp.json()["workflow_id"]

    get_session_resp = client.get(f"/api/agent/sessions/{session_id}")
    assert get_session_resp.status_code == 200
    assert get_session_resp.json()["workflow_id"] == workflow_id

    workflow_resp = client.get(f"/api/workflows/{workflow_id}")
    assert workflow_resp.status_code == 200
    assert workflow_resp.json()["graph"]["nodes"][1]["type"] == "llm"


def test_apply_agent_session_is_idempotent(client, db):
    provider_resp = client.post(
        "/api/providers",
        json={
            "type": "openai",
            "name": "Planner OpenAI",
            "api_key": "sk-test",
        },
    )
    assert provider_resp.status_code == 201

    session_resp = client.post(
        "/api/agent/sessions",
        json={"goal": "做一期播客"},
    )
    session_id = session_resp.json()["session_id"]

    first = client.post(f"/api/agent/sessions/{session_id}/apply")
    second = client.post(f"/api/agent/sessions/{session_id}/apply")

    assert first.status_code == 200
    assert second.status_code == 200
    assert first.json()["workflow_id"] == second.json()["workflow_id"]
    assert db.query(Workflow).count() == 1
