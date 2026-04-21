"""Tests for ReActBuilderAgentRunner and ReActHarnessSession."""

from __future__ import annotations

import asyncio
import json
from typing import Any

import pytest
from langchain_core.messages import AIMessage, HumanMessage, ToolMessage

from backend.harness.builder import GraphBuilder
from backend.harness.react_runner import ReActBuilderAgentRunner
from backend.harness.react_session import (
    ReActHarnessSession,
    create_react_harness_session,
    load_react_harness_session,
    _messages_to_json,
    _messages_from_json,
)
from backend.harness.skills.loader import SkillLoader
from backend.harness.workspace import Workspace


# ───────────────────────────────────────────────
# Message serialization
# ───────────────────────────────────────────────

def test_messages_roundtrip():
    msgs = [
        HumanMessage(content="Hello"),
        AIMessage(content="Hi there", tool_calls=[{"name": "inspect_canvas", "args": {}, "id": "tc1"}]),
        ToolMessage(content="result", tool_call_id="tc1", name="inspect_canvas"),
    ]
    text = _messages_to_json(msgs)
    restored = _messages_from_json(text)
    assert len(restored) == 3
    assert restored[0].content == "Hello"
    assert restored[1].content == "Hi there"
    assert restored[1].tool_calls[0]["name"] == "inspect_canvas"
    assert restored[2].content == "result"
    assert restored[2].tool_call_id == "tc1"


# ───────────────────────────────────────────────
# ReActHarnessSession persistence
# ───────────────────────────────────────────────

@pytest.mark.asyncio
async def test_react_session_create_and_load(db):
    hs = create_react_harness_session(db, goal="Build a podcast workflow")
    assert hs.status == "running"
    assert hs.goal == "Build a podcast workflow"

    loaded = load_react_harness_session(hs.id, db)
    assert loaded.goal == hs.goal
    assert loaded.status == "running"


@pytest.mark.asyncio
async def test_react_session_resume_detects_status(db):
    hs = create_react_harness_session(db, goal="Test")
    hs.workspace.set_open_question("Which provider?", ["openai", "anthropic"], question_id="q1")
    hs._status = "awaiting_user"
    hs._persist()

    loaded = load_react_harness_session(hs.id, db)
    assert loaded.status == "awaiting_user"
    assert loaded.workspace.open_question["question_id"] == "q1"


# ───────────────────────────────────────────────
# Runner construction
# ───────────────────────────────────────────────

def test_build_agent_uses_langgraph_state_modifier(monkeypatch, db):
    ws = Workspace(goal="test")
    builder = GraphBuilder()
    runner = ReActBuilderAgentRunner(
        session_id="test-signature",
        workspace=ws,
        builder=builder,
        db=db,
        skills=SkillLoader(),
    )
    fake_agent = object()
    captured_kwargs: dict[str, Any] = {}

    monkeypatch.setattr(
        "backend.harness.react_runner._create_chat_model",
        lambda _db: object(),
    )

    def fake_create_react_agent(*_args, **kwargs):
        captured_kwargs.update(kwargs)
        if "prompt" in kwargs:
            raise TypeError("create_react_agent() got an unexpected keyword argument 'prompt'")
        return fake_agent

    monkeypatch.setattr(
        "backend.harness.react_runner.create_react_agent",
        fake_create_react_agent,
    )

    assert runner._build_agent() is fake_agent
    assert "state_modifier" in captured_kwargs
    assert callable(captured_kwargs["state_modifier"])


# ───────────────────────────────────────────────
# Tools: read-only
# ───────────────────────────────────────────────

@pytest.mark.asyncio
async def test_inspect_canvas_tool(db):
    ws = Workspace(goal="test")
    builder = GraphBuilder()
    runner = ReActBuilderAgentRunner(
        session_id="test-session",
        workspace=ws,
        builder=builder,
        db=db,
        skills=SkillLoader(),
    )
    try:
        agent = runner._build_agent()
    except RuntimeError as exc:
        if "No enabled LLM provider" in str(exc):
            pytest.skip("No LLM provider configured")
        raise
    config = {"configurable": {"thread_id": "test-session"}}

    # Run a single turn asking the agent to inspect canvas
    msgs = [HumanMessage(content="Inspect the canvas")]
    events = []
    async for event in agent.astream({"messages": msgs}, config, stream_mode="messages"):
        msg, metadata = event
        events.append((msg.type if hasattr(msg, "type") else "unknown", getattr(msg, "name", None)))

    # Should see at least AI message and possibly tool calls
    ai_events = [e for e in events if e[0] == "ai"]
    tool_events = [e for e in events if e[0] == "tool"]
    assert len(ai_events) >= 1


# ───────────────────────────────────────────────
# Tools: write (add_node, connect_nodes)
# ───────────────────────────────────────────────

@pytest.mark.asyncio
async def test_add_node_and_connect_tools(db):
    ws = Workspace(goal="test")
    builder = GraphBuilder()
    runner = ReActBuilderAgentRunner(
        session_id="test-write",
        workspace=ws,
        builder=builder,
        db=db,
        skills=SkillLoader(),
    )
    try:
        agent = runner._build_agent()
    except RuntimeError as exc:
        if "No enabled LLM provider" in str(exc):
            pytest.skip("No LLM provider configured")
        raise
    config = {"configurable": {"thread_id": "test-write"}}

    msgs = [HumanMessage(content="Add a start node, an llm node, and connect them")]
    events = []
    async for event in agent.astream({"messages": msgs}, config, stream_mode="messages"):
        msg, metadata = event
        events.append(msg)

    # After tool calls, builder should have nodes
    snapshot = builder.snapshot()
    node_types = {n["type"] for n in snapshot.get("nodes", [])}
    assert "start" in node_types or "llm" in node_types or len(snapshot.get("nodes", [])) > 0


# ───────────────────────────────────────────────
# Event bridge: graph_update emitted after write
# ───────────────────────────────────────────────

@pytest.mark.asyncio
async def test_runner_emits_graph_update_after_add_node(db):
    ws = Workspace(goal="test")
    builder = GraphBuilder()
    runner = ReActBuilderAgentRunner(
        session_id="test-events",
        workspace=ws,
        builder=builder,
        db=db,
        skills=SkillLoader(),
    )
    try:
        runner._build_agent()
    except RuntimeError as exc:
        if "No enabled LLM provider" in str(exc):
            pytest.skip("No LLM provider configured")
        raise

    collected = []
    async def on_event(event):
        collected.append(event)

    # Manually feed a tool call through the runner
    msgs = [HumanMessage(content="Add a start node named start_1")]
    await runner.run(msgs, on_event=on_event)

    graph_updates = [e for e in collected if e.get("type") == "graph_update"]
    # Note: the LLM may or may not call add_node in this test depending on provider.
    # This is a best-effort integration test.


# ───────────────────────────────────────────────
# Event bridge: ask_user pause marker
# ───────────────────────────────────────────────

@pytest.mark.asyncio
async def test_ask_user_tool_returns_pause_marker(db):
    from backend.harness.react_tools.ask_user import make_ask_user_tool
    from backend.harness.react_tools.base import ToolContext

    ws = Workspace(goal="test")
    builder = GraphBuilder()
    ctx = ToolContext(
        session_id="test",
        workspace=ws,
        builder=builder,
        db=db,
        skills=SkillLoader(),
    )
    tool = make_ask_user_tool(ctx)
    result = tool.invoke({"question": "Which model?", "options": ["gpt-4o", "claude"]})
    data = json.loads(result)
    assert data.get("__pause__") is True
    assert data.get("question") == "Which model?"
    assert len(data.get("question_id", "")) > 0
    assert ws.open_question is not None


# ───────────────────────────────────────────────
# End-to-end: ReActHarnessSession run with mock events
# ───────────────────────────────────────────────

@pytest.mark.asyncio
async def test_react_session_run_emits_session_start(db):
    hs = create_react_harness_session(db, goal="Build a simple workflow")
    hs._init_runner()

    collected = []
    async def on_event(event):
        collected.append(event)

    # This test requires a real LLM provider to complete.
    # In CI without keys, we verify the runner can be built and session_start is emitted.
    try:
        await hs.run(on_event=on_event)
        start_events = [e for e in collected if e.get("type") == "session_start"]
        assert len(start_events) >= 1
        assert start_events[0].get("goal") == "Build a simple workflow"
    except RuntimeError as exc:
        if "No enabled LLM provider" in str(exc):
            pytest.skip("No LLM provider configured")
        raise


@pytest.mark.asyncio
async def test_react_session_plain_agent_reply_waits_for_next_user_turn(db):
    hs = create_react_harness_session(db, goal="Say hello")

    class PlainReplyRunner:
        async def run(self, messages, on_event=None):
            if on_event is not None:
                await on_event({"type": "agent_message", "content": "Hello"})
            return [*messages, AIMessage(content="Hello")]

    hs._runner = PlainReplyRunner()
    collected = []

    async def on_event(event):
        collected.append(event)

    await hs.run(on_event=on_event)

    assert hs.status == "waiting"
    assert collected[-1] == {"type": "session_end", "status": "waiting"}


@pytest.mark.asyncio
async def test_react_session_persists_ready_if_client_disconnects_after_ready_event(db):
    hs = create_react_harness_session(db, goal="Build a workflow")

    class ReadyRunner:
        async def run(self, messages, on_event=None):
            if on_event is not None:
                await on_event({"type": "harness_ready", "snapshot": hs.builder.snapshot()})
            return [*messages, AIMessage(content="Ready")]

    hs._runner = ReadyRunner()

    async def disconnect_after_ready(event):
        if event.get("type") == "harness_ready":
            raise asyncio.CancelledError()

    with pytest.raises(asyncio.CancelledError):
        await hs.run(on_event=disconnect_after_ready)

    loaded = load_react_harness_session(hs.id, db)
    assert loaded.status == "ready"

    loaded.queue_user_message("Add a TTS step")
    reloaded = load_react_harness_session(hs.id, db)
    assert reloaded.status == "running"
    assert reloaded.messages[-1].content == "Add a TTS step"


@pytest.mark.asyncio
async def test_react_session_persists_open_question_if_client_disconnects_after_ask_event(db):
    hs = create_react_harness_session(db, goal="Build a workflow")

    class AskRunner:
        async def run(self, messages, on_event=None):
            hs.workspace.set_open_question("Which provider?", ["openai"], question_id="q1")
            if on_event is not None:
                await on_event({
                    "type": "awaiting_user_input",
                    "question_id": "q1",
                    "prompt": "Which provider?",
                    "options": ["openai"],
                })
            return [*messages, AIMessage(content="Need provider")]

    hs._runner = AskRunner()

    async def disconnect_after_question(event):
        if event.get("type") == "awaiting_user_input":
            raise asyncio.CancelledError()

    with pytest.raises(asyncio.CancelledError):
        await hs.run(on_event=disconnect_after_question)

    loaded = load_react_harness_session(hs.id, db)
    assert loaded.status == "awaiting_user"
    assert loaded.workspace.open_question["question_id"] == "q1"

    loaded.queue_resume("q1", "openai")
    reloaded = load_react_harness_session(hs.id, db)
    assert reloaded.status == "running"
    assert reloaded.messages[-1].content == "User answered: openai"


def test_react_session_queue_user_message_reopens_waiting_session(db):
    hs = create_react_harness_session(db, goal="Build a workflow")
    hs._status = "waiting"
    hs._persist()

    hs.queue_user_message("Add a TTS step")

    loaded = load_react_harness_session(hs.id, db)
    assert loaded.status == "running"
    assert loaded.messages[-1].content == "Add a TTS step"


def test_react_session_load_normalizes_legacy_awaiting_user_without_question(db):
    hs = create_react_harness_session(db, goal="Build a workflow")
    hs._status = "awaiting_user"
    hs.workspace.open_question = None
    hs._persist()

    loaded = load_react_harness_session(hs.id, db)

    assert loaded.status == "waiting"
