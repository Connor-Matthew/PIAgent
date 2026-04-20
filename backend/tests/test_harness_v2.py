"""PIAgent Harness v2 tests.

Mocks the LLM (LeadAgent.decide) to test the orchestration loop, pause/resume,
validation recovery, skill loading, stuck detection, and preferences.
"""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest
from sqlalchemy.orm import Session

from backend.harness.builder import GraphBuilder
from backend.harness.tools import ToolRegistry
from backend.harness.tools.list_node_types import ListNodeTypesTool
from backend.harness.tools.list_skills import ListSkillsTool
from backend.harness.schemas import (
    AddEdgeAction,
    AddNodeAction,
    AskUser,
    CallTool,
    Decision,
    DeleteNodeAction,
    Finalize,
    LoadSkill,
    ProposeAction,
    UpdateNodeConfigAction,
)
from backend.harness.session import (
    HarnessSession,
    create_harness_session,
    load_harness_session,
)
from backend.harness.skills.loader import SkillLoader
from backend.harness.validators import validate_graph
from backend.harness.workspace import Workspace
from backend.models.project_preference import ProjectPreference
from backend.models.provider import Provider


# ── helpers ──

def _make_decision_sequence(decisions: list[Decision]):
    """Return a callable that yields decisions sequentially."""
    idx = 0

    def _decide(workspace):
        nonlocal idx
        if idx < len(decisions):
            d = decisions[idx]
            idx += 1
            return d
        # Default: keep finalizing once out of scripted decisions
        return Finalize(reason="default")

    return _decide


# ── builder tests ──

def test_builder_add_node():
    b = GraphBuilder()
    b.apply(AddNodeAction(node_type="start", node_id="start_1"))
    snap = b.snapshot()
    assert len(snap["nodes"]) == 1
    assert snap["nodes"][0]["id"] == "start_1"
    assert snap["nodes"][0]["type"] == "start"


def test_builder_add_edge():
    b = GraphBuilder()
    b.apply(AddNodeAction(node_type="start", node_id="s1"))
    b.apply(AddNodeAction(node_type="end", node_id="e1"))
    b.apply(AddEdgeAction(source="s1", target="e1"))
    snap = b.snapshot()
    assert len(snap["edges"]) == 1
    assert snap["edges"][0]["source"] == "s1"


def test_builder_delete_node_cascades_edges():
    b = GraphBuilder()
    b.apply(AddNodeAction(node_type="start", node_id="s1"))
    b.apply(AddNodeAction(node_type="end", node_id="e1"))
    b.apply(AddEdgeAction(source="s1", target="e1"))
    b.apply(DeleteNodeAction(node_id="e1"))
    snap = b.snapshot()
    assert len(snap["nodes"]) == 1
    assert len(snap["edges"]) == 0


def test_builder_add_node_with_parent_id():
    b = GraphBuilder()
    b.apply(AddNodeAction(node_type="if_else", node_id="if1"))
    b.apply(AddNodeAction(node_type="llm", node_id="n1", parent_id="if1"))
    snap = b.snapshot()
    n1 = next(n for n in snap["nodes"] if n["id"] == "n1")
    assert n1["parentId"] == "if1"


def test_builder_delete_node_cascades_children():
    b = GraphBuilder()
    b.apply(AddNodeAction(node_type="if_else", node_id="if1"))
    b.apply(AddNodeAction(node_type="llm", node_id="n1", parent_id="if1"))
    b.apply(AddNodeAction(node_type="llm", node_id="n2", parent_id="if1"))
    b.apply(AddEdgeAction(source="n1", target="n2"))
    b.apply(DeleteNodeAction(node_id="if1"))
    snap = b.snapshot()
    assert len(snap["nodes"]) == 0
    assert len(snap["edges"]) == 0


# ── validator tests ──

def test_validator_missing_start_and_end():
    findings = validate_graph({"nodes": [], "edges": []})
    codes = {f.code for f in findings}
    assert "missing_start" in codes
    assert "missing_end" in codes


def test_validator_cycle():
    graph = {
        "nodes": [
            {"id": "s1", "type": "start"},
            {"id": "n1", "type": "llm"},
            {"id": "e1", "type": "end"},
        ],
        "edges": [
            {"id": "s1-n1", "source": "s1", "target": "n1"},
            {"id": "n1-e1", "source": "n1", "target": "e1"},
            {"id": "e1-s1", "source": "e1", "target": "s1"},
        ],
    }
    findings = validate_graph(graph)
    assert any(f.code == "cycle" for f in findings)


def test_validator_too_simple():
    graph = {
        "nodes": [
            {"id": "s1", "type": "start"},
            {"id": "e1", "type": "end"},
        ],
        "edges": [
            {"id": "s1-e1", "source": "s1", "target": "e1"},
        ],
    }
    findings = validate_graph(graph)
    assert any(f.code == "too_simple" for f in findings)


def test_validator_cross_scope_edge():
    graph = {
        "nodes": [
            {"id": "s1", "type": "start"},
            {"id": "if1", "type": "if_else"},
            {"id": "n1", "type": "llm", "parentId": "if1"},
            {"id": "e1", "type": "end"},
        ],
        "edges": [
            {"id": "s1-if1", "source": "s1", "target": "if1"},
            {"id": "if1-e1", "source": "if1", "target": "e1"},
            {"id": "n1-e1", "source": "n1", "target": "e1"},  # illegal: child -> external
        ],
    }
    findings = validate_graph(graph)
    assert any(f.code == "cross_scope_edge" for f in findings)


def test_validator_subgraph_cycle():
    graph = {
        "nodes": [
            {"id": "s1", "type": "start"},
            {"id": "if1", "type": "if_else"},
            {"id": "n1", "type": "llm", "parentId": "if1"},
            {"id": "n2", "type": "llm", "parentId": "if1"},
            {"id": "e1", "type": "end"},
        ],
        "edges": [
            {"id": "s1-if1", "source": "s1", "target": "if1"},
            {"id": "if1-e1", "source": "if1", "target": "e1"},
            {"id": "n1-n2", "source": "n1", "target": "n2"},
            {"id": "n2-n1", "source": "n2", "target": "n1"},  # cycle inside subgraph
        ],
    }
    findings = validate_graph(graph)
    assert any(f.code == "subgraph_cycle" for f in findings)


def test_validator_subgraph_no_entry():
    graph = {
        "nodes": [
            {"id": "s1", "type": "start"},
            {"id": "if1", "type": "if_else"},
            {"id": "n1", "type": "llm", "parentId": "if1"},
            {"id": "n2", "type": "llm", "parentId": "if1"},
            {"id": "e1", "type": "end"},
        ],
        "edges": [
            {"id": "s1-if1", "source": "s1", "target": "if1"},
            {"id": "if1-e1", "source": "if1", "target": "e1"},
            {"id": "n1-n2", "source": "n1", "target": "n2"},  # n1 has incoming from nowhere in subgraph
        ],
    }
    findings = validate_graph(graph)
    # n1 and n2 both have no incoming edges within the subgraph, so entry_nodes = {n1, n2}
    # This should NOT trigger subgraph_no_entry
    assert not any(f.code == "subgraph_no_entry" for f in findings)

    # Now make every child have an incoming edge from another child
    graph2 = {
        "nodes": [
            {"id": "s1", "type": "start"},
            {"id": "if1", "type": "if_else"},
            {"id": "n1", "type": "llm", "parentId": "if1"},
            {"id": "n2", "type": "llm", "parentId": "if1"},
            {"id": "e1", "type": "end"},
        ],
        "edges": [
            {"id": "s1-if1", "source": "s1", "target": "if1"},
            {"id": "if1-e1", "source": "if1", "target": "e1"},
            {"id": "n1-n2", "source": "n1", "target": "n2"},
            {"id": "n2-n1", "source": "n2", "target": "n1"},
        ],
    }
    findings2 = validate_graph(graph2)
    assert any(f.code == "subgraph_no_entry" for f in findings2)


def test_validator_nested_graph_no_false_cycle():
    """A flat nested graph with parentId should not trigger a false cycle."""
    graph = {
        "nodes": [
            {"id": "s1", "type": "start"},
            {"id": "if1", "type": "if_else"},
            {"id": "n1", "type": "llm", "parentId": "if1"},
            {"id": "e1", "type": "end"},
        ],
        "edges": [
            {"id": "s1-if1", "source": "s1", "target": "if1"},
            {"id": "if1-e1", "source": "if1", "target": "e1"},
        ],
    }
    findings = validate_graph(graph)
    assert not any(f.code == "cycle" for f in findings)
    assert not any(f.code == "cross_scope_edge" for f in findings)


# ── workspace tests ──

def test_workspace_snapshot_roundtrip():
    ws = Workspace(goal="test")
    ws.bootstrap("test", preferences={"foo": "bar"})
    snap = ws.to_snapshot()
    ws2 = Workspace()
    ws2.from_snapshot(snap)
    assert ws2.goal == "test"
    assert ws2.preferences == {"foo": "bar"}


def test_workspace_observation_includes_loaded_skill_content():
    ws = Workspace(goal="podcast")
    ws.bootstrap("podcast")
    ws.record_skill("tts_podcast", "# TTS 播客 Skill\n\n先写稿，再合成语音。")

    rendered = ws.observation().render()

    assert "tts_podcast" in rendered
    assert "先写稿，再合成语音" in rendered


# ── session loop tests (mocked LLM) ──

@pytest.mark.asyncio
async def test_harness_session_basic(db: Session):
    """A simple goal: model lists node types, adds start+llm+end, finalizes."""
    # Seed a provider so validation passes
    db.add(Provider(type="openai", name="test", api_key_encrypted="enc", enabled=True, category="llm"))
    db.commit()

    hs = create_harness_session(db, goal="build a simple llm workflow")
    hs.setup_tools(MagicMock())  # minimal tool mock
    hs.init_lead_agent()

    decisions = [
        CallTool(tool="list_node_types", args={}),
        ProposeAction(action=AddNodeAction(node_type="start", node_id="start_1")),
        ProposeAction(action=AddNodeAction(node_type="llm", node_id="llm_1", config={"provider_id": 1})),
        ProposeAction(action=AddNodeAction(node_type="end", node_id="end_1")),
        ProposeAction(action=AddEdgeAction(source="start_1", target="llm_1")),
        ProposeAction(action=AddEdgeAction(source="llm_1", target="end_1")),
        Finalize(reason="looks good"),
    ]

    with patch.object(hs.lead_agent, "decide", side_effect=_make_decision_sequence(decisions)):
        events: list[dict] = []
        async def emit(ev):
            events.append(ev)
        await hs.run(on_event=emit)

    assert hs.status == "ready"
    assert any(e["type"] == "harness_ready" for e in events)
    snap = hs.builder.snapshot()
    assert len(snap["nodes"]) == 3
    assert len(snap["edges"]) == 2


@pytest.mark.asyncio
async def test_harness_validator_recovery(db: Session):
    """Model proposes a graph missing 'end', gets validator errors, then fixes."""
    # Seed a provider so the fixed graph passes validation
    db.add(Provider(type="openai", name="test", api_key_encrypted="enc", enabled=True, category="llm"))
    db.commit()

    hs = create_harness_session(db, goal="build a workflow")
    hs.setup_tools(MagicMock())
    hs.init_lead_agent()

    decisions = [
        # First attempt: missing end
        ProposeAction(action=AddNodeAction(node_type="start", node_id="start_1")),
        ProposeAction(action=AddNodeAction(node_type="llm", node_id="llm_1", config={"provider_id": 1})),
        ProposeAction(action=AddEdgeAction(source="start_1", target="llm_1")),
        Finalize(reason="missing end on purpose"),
        # Second attempt: fix by adding end
        ProposeAction(action=AddNodeAction(node_type="end", node_id="end_1")),
        ProposeAction(action=AddEdgeAction(source="llm_1", target="end_1")),
        Finalize(reason="fixed"),
    ]

    with patch.object(hs.lead_agent, "decide", side_effect=_make_decision_sequence(decisions)):
        events: list[dict] = []
        async def emit(ev):
            events.append(ev)
        await hs.run(on_event=emit)

    assert hs.status == "ready"
    validator_reports = [e for e in events if e["type"] == "validator_report"]
    # First finalize should have missing_end error
    assert any(
        f["code"] == "missing_end"
        for e in validator_reports
        for f in e.get("findings", [])
    )


@pytest.mark.asyncio
async def test_harness_ask_user_pause_resume(db: Session):
    """AskUser decision pauses the loop; resume continues it."""
    hs = create_harness_session(db, goal="ambiguous goal")
    hs.setup_tools(MagicMock())
    hs.init_lead_agent()

    pre_pause = [
        AskUser(question="What kind of output?", options=["text", "audio"]),
    ]
    post_resume = [
        ProposeAction(action=AddNodeAction(node_type="start", node_id="start_1")),
        ProposeAction(action=AddNodeAction(node_type="end", node_id="end_1")),
        ProposeAction(action=AddEdgeAction(source="start_1", target="end_1")),
        Finalize(reason="done"),
    ]

    with patch.object(hs.lead_agent, "decide", side_effect=_make_decision_sequence(pre_pause)):
        events: list[dict] = []
        async def emit(ev):
            events.append(ev)
        await hs.run(on_event=emit)

    assert hs.status == "awaiting_user"
    assert any(e["type"] == "awaiting_user_input" for e in events)

    # Resume
    with patch.object(hs.lead_agent, "decide", side_effect=_make_decision_sequence(post_resume)):
        events2: list[dict] = []
        async def emit2(ev):
            events2.append(ev)
        question_id = hs.workspace.open_question["question_id"]
        await hs.resume(question_id=question_id, answer="text", on_event=emit2)

    assert hs.status == "ready"
    assert any(e["type"] == "user_resumed" for e in events2)


@pytest.mark.asyncio
async def test_harness_skill_load(db: Session):
    """LoadSkill decision pulls markdown content into facts ledger."""
    hs = create_harness_session(db, goal="use rag")
    hs.setup_tools(MagicMock())
    hs.init_lead_agent()

    decisions = [
        LoadSkill(skill="rag_qa"),
        Finalize(reason="skill loaded"),
    ]

    with patch.object(hs.lead_agent, "decide", side_effect=_make_decision_sequence(decisions)):
        events: list[dict] = []
        async def emit(ev):
            events.append(ev)
        await hs.run(on_event=emit)

    assert any(e["type"] == "skill_loaded" for e in events)
    # Facts ledger should contain the skill
    facts = hs.workspace.facts.to_dict()
    assert "rag_qa" in facts.get("skills", {})


@pytest.mark.asyncio
async def test_harness_duplicate_skill_load_does_not_immediately_stuck(db: Session):
    """Reloading an already-loaded skill should produce an observation, not instant stuck."""
    hs = create_harness_session(db, goal="use tts")
    hs.setup_tools(MagicMock())
    hs.init_lead_agent()

    decisions = [
        LoadSkill(skill="tts_podcast"),
        LoadSkill(skill="tts_podcast"),
        AskUser(question="继续哪一步？", options=["构图", "结束"]),
    ]

    with patch.object(hs.lead_agent, "decide", side_effect=_make_decision_sequence(decisions)):
        events: list[dict] = []

        async def emit(ev):
            events.append(ev)

        await hs.run(on_event=emit)

    assert hs.status == "awaiting_user"
    assert not any(e["type"] == "harness_stuck" for e in events)
    assert any(
        e["type"] == "skill_loaded" and e.get("cached") is True
        for e in events
    )
    facts = hs.workspace.facts.to_dict()
    assert any(
        err["source"] == "skill" and "already loaded" in err["message"]
        for err in facts.get("errors", [])
    )


@pytest.mark.asyncio
async def test_harness_stuck_detection(db: Session):
    """Repeated identical decisions trigger stuck detection."""
    hs = create_harness_session(db, goal="stuck test")
    hs.setup_tools(MagicMock())
    hs.init_lead_agent()

    # Emit the same CallTool decision 3 times
    decisions = [CallTool(tool="list_node_types", args={})] * 3

    with patch.object(hs.lead_agent, "decide", side_effect=_make_decision_sequence(decisions)):
        events: list[dict] = []
        async def emit(ev):
            events.append(ev)
        await hs.run(on_event=emit)

    assert hs.status == "failed"
    assert any(e["type"] == "harness_stuck" for e in events)


@pytest.mark.asyncio
async def test_harness_run_exception_emits_one_failed_session_end(db: Session):
    """Unexpected lead loop errors should produce one terminal failure event."""
    hs = create_harness_session(db, goal="explode")
    hs.setup_tools(MagicMock())
    hs.init_lead_agent()

    def explode(workspace):
        raise RuntimeError("boom")

    with patch.object(hs.lead_agent, "decide", side_effect=explode):
        events: list[dict] = []

        async def emit(ev):
            events.append(ev)

        with pytest.raises(RuntimeError, match="boom"):
            await hs.run(on_event=emit)

    session_end_events = [event for event in events if event["type"] == "session_end"]
    assert session_end_events == [
        {"type": "session_end", "status": "failed", "reason": "boom"}
    ]
    assert hs.status == "failed"


@pytest.mark.asyncio
async def test_harness_preference_write(db: Session):
    """After apply(), preferences should be updated if graph changed."""
    # Seed a provider so validation passes
    db.add(Provider(type="openai", name="test", api_key_encrypted="enc", enabled=True, category="llm"))
    db.commit()

    hs = create_harness_session(db, goal="build llm workflow")
    hs.setup_tools(MagicMock())
    hs.init_lead_agent()

    decisions = [
        ProposeAction(action=AddNodeAction(node_type="start", node_id="start_1")),
        ProposeAction(action=AddNodeAction(node_type="llm", node_id="llm_1", config={"provider_id": 1})),
        ProposeAction(action=AddNodeAction(node_type="end", node_id="end_1")),
        ProposeAction(action=AddEdgeAction(source="start_1", target="llm_1")),
        ProposeAction(action=AddEdgeAction(source="llm_1", target="end_1")),
        Finalize(reason="done"),
    ]

    with patch.object(hs.lead_agent, "decide", side_effect=_make_decision_sequence(decisions)):
        events: list[dict] = []
        async def emit(ev):
            events.append(ev)
        await hs.run(on_event=emit)

    assert hs.status == "ready"

    # Apply (no user edits, so preferences should not change much)
    result = await hs.apply()
    assert "workflow_id" in result
    assert hs.status == "applied"

    # Verify a preference row exists
    pref = db.query(ProjectPreference).filter(ProjectPreference.key == "default").first()
    assert pref is not None


# ── skill loader tests ──

def test_skill_loader_catalog():
    loader = SkillLoader()
    catalog = loader.catalog()
    names = {s["name"] for s in catalog}
    assert "rag_qa" in names
    assert "llm_basic" in names


def test_skill_loader_load():
    loader = SkillLoader()
    content = loader.load("simple_pipeline")
    assert "Start" in content
    assert "LLM" in content
    # Second load should return cached content
    assert loader.load("simple_pipeline") == content


def test_tool_registry_render_catalog_handles_no_input_tools():
    registry = ToolRegistry()
    registry.register(ListNodeTypesTool())
    registry.register(ListSkillsTool())

    catalog = registry.render_catalog()

    assert "## list_node_types" in catalog
    assert "## list_skills" in catalog
    assert '"type": "object"' in catalog


# ── validators pure-function contract ──

def test_validators_no_llm_reference():
    """Verify validators.py does not import or reference any LLM client."""
    import inspect
    from backend.harness import validators as vmod
    source = inspect.getsource(vmod)
    assert "llm" not in source.lower() or "validate_graph" in source.lower()
    # More precise: no calls to structured_invoke, chat_model, etc.
    banned = ["structured_invoke", "chat_model", "ainvoke", "openai", "anthropic"]
    for term in banned:
        assert term not in source.lower(), f"validators.py should not reference {term}"


@pytest.mark.asyncio
async def test_load_harness_session_restores_builder(db: Session):
    """After load_harness_session, the builder is repopulated from workspace.graph_draft."""
    db.add(Provider(type="openai", name="test", api_key_encrypted="enc", enabled=True, category="llm"))
    db.commit()

    hs = create_harness_session(db, goal="build")
    hs.setup_tools(MagicMock())
    hs.init_lead_agent()

    decisions = [
        ProposeAction(action=AddNodeAction(node_type="start", node_id="start_1")),
        ProposeAction(action=AddNodeAction(node_type="llm", node_id="llm_1", config={"provider_id": 1})),
        ProposeAction(action=AddNodeAction(node_type="end", node_id="end_1")),
        ProposeAction(action=AddEdgeAction(source="start_1", target="llm_1")),
        ProposeAction(action=AddEdgeAction(source="llm_1", target="end_1")),
        Finalize(reason="done"),
    ]

    with patch.object(hs.lead_agent, "decide", side_effect=_make_decision_sequence(decisions)):
        async def emit(ev):
            pass
        await hs.run(on_event=emit)

    assert hs.status == "ready"

    # Simulate a fresh API call loading the session for apply
    hs2 = load_harness_session(hs.id, db)
    snap = hs2.builder.snapshot()
    assert len(snap["nodes"]) == 3
    assert len(snap["edges"]) == 2
    assert {n["id"] for n in snap["nodes"]} == {"start_1", "llm_1", "end_1"}


@pytest.mark.asyncio
async def test_harness_ask_user_pause_then_load_resume_and_apply(db: Session):
    """AskUser pauses the session; after load_harness_session + resume the builder
    state is intact and the graph can be finalized and applied."""
    db.add(Provider(type="openai", name="test", api_key_encrypted="enc", enabled=True, category="llm"))
    db.commit()

    hs = create_harness_session(db, goal="build a workflow")
    hs.setup_tools(MagicMock())
    hs.init_lead_agent()

    pre_pause = [
        ProposeAction(action=AddNodeAction(node_type="start", node_id="start_1")),
        ProposeAction(action=AddNodeAction(node_type="llm", node_id="llm_1", config={"provider_id": 1})),
        AskUser(question="Continue?", options=["yes", "no"]),
    ]
    post_resume = [
        ProposeAction(action=AddNodeAction(node_type="end", node_id="end_1")),
        ProposeAction(action=AddEdgeAction(source="start_1", target="llm_1")),
        ProposeAction(action=AddEdgeAction(source="llm_1", target="end_1")),
        Finalize(reason="done"),
    ]

    with patch.object(hs.lead_agent, "decide", side_effect=_make_decision_sequence(pre_pause)):
        async def emit(ev):
            pass
        await hs.run(on_event=emit)

    assert hs.status == "awaiting_user"
    # Builder should have 2 nodes before the pause
    assert len(hs.builder.snapshot()["nodes"]) == 2

    # Simulate fresh process loading the session from DB
    hs2 = load_harness_session(hs.id, db)
    hs2.setup_tools(MagicMock())
    hs2.init_lead_agent()
    assert hs2.status == "awaiting_user"
    # Builder must be restored from graph_draft
    snap2 = hs2.builder.snapshot()
    assert len(snap2["nodes"]) == 2
    assert {n["id"] for n in snap2["nodes"]} == {"start_1", "llm_1"}

    # Resume and finish the graph
    with patch.object(hs2.lead_agent, "decide", side_effect=_make_decision_sequence(post_resume)):
        async def emit2(ev):
            pass
        qid = hs2.workspace.open_question["question_id"]
        await hs2.resume(question_id=qid, answer="yes", on_event=emit2)

    assert hs2.status == "ready"
    final_snap = hs2.builder.snapshot()
    assert len(final_snap["nodes"]) == 3
    assert len(final_snap["edges"]) == 2

    # Apply should create a workflow without error
    result = await hs2.apply()
    assert "workflow_id" in result
    assert hs2.status == "applied"


def test_builder_snapshot_is_canonical_v2():
    b = GraphBuilder()
    b.apply(AddNodeAction(node_type="if_else", node_id="if_1", config={"branches": [{"id": "true"}]}))
    b.apply(
        AddNodeAction(
            node_type="llm",
            node_id="llm_true",
            parent_id="if_1",
            config={"branchId": "true", "provider_id": 1},
        )
    )

    snap = b.snapshot()
    child = next(n for n in snap["nodes"] if n["id"] == "llm_true")

    assert snap["version"] == 2
    assert child["parentId"] == "if_1"
    assert child["branchId"] == "true"
    assert child["config"] == {"provider_id": 1}
    assert "data" not in child


def test_harness_validator_accepts_v2_provider_config(db: Session):
    db.add(Provider(type="openai", name="test", api_key_encrypted="enc", enabled=True, category="llm"))
    db.commit()

    graph = {
        "version": 2,
        "nodes": [
            {"id": "start_1", "type": "start", "config": {}},
            {"id": "llm_1", "type": "llm", "config": {"provider_id": 1}},
            {"id": "end_1", "type": "end", "config": {"outputs": []}},
        ],
        "edges": [
            {"source": "start_1", "target": "llm_1"},
            {"source": "llm_1", "target": "end_1"},
        ],
    }

    findings = validate_graph(graph, db=db)

    assert not [f for f in findings if f.severity == "error"]
