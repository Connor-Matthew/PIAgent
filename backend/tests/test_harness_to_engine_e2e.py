"""E2E tests: harness generates a graph → apply persists it → engine executes it.

These tests guard against divergence between harness validation and engine
compilation/execution, especially for control-flow subgraphs.
"""

from __future__ import annotations

import json
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from sqlalchemy.orm import Session

from backend.core.engine import ExecutionEngine
from backend.harness.schemas import (
    AddEdgeAction,
    AddNodeAction,
    Finalize,
    ProposeAction,
    UpdateNodeConfigAction,
)
from backend.harness.session import create_harness_session, load_harness_session
from backend.models.provider import Provider
from backend.models.workflow import Workflow


# ── helpers ──

def _make_decision_sequence(decisions):
    """Return a callable that yields decisions sequentially."""
    idx = 0

    def _decide(workspace):
        nonlocal idx
        if idx < len(decisions):
            d = decisions[idx]
            idx += 1
            return d
        return Finalize(reason="default")

    return _decide


# ── test case 1: simple linear workflow ──

@pytest.mark.asyncio
async def test_harness_to_engine_linear_workflow(db: Session):
    """Harness builds Start → LLM → End; engine executes it end-to-end."""
    db.add(
        Provider(
            type="openai",
            name="test",
            api_key_encrypted="enc",
            enabled=True,
            category="llm",
        )
    )
    db.commit()

    hs = create_harness_session(db, goal="build a simple echo workflow")
    hs.setup_tools(MagicMock())
    hs.init_lead_agent()

    decisions = [
        ProposeAction(action=AddNodeAction(node_type="start", node_id="start_1")),
        ProposeAction(
            action=AddNodeAction(
                node_type="llm",
                node_id="llm_1",
                config={"provider_id": 1},
            )
        ),
        ProposeAction(action=AddNodeAction(node_type="end", node_id="end_1")),
        ProposeAction(action=AddEdgeAction(source="start_1", target="llm_1")),
        ProposeAction(action=AddEdgeAction(source="llm_1", target="end_1")),
        Finalize(reason="done"),
    ]

    with patch.object(
        hs.lead_agent, "decide", side_effect=_make_decision_sequence(decisions)
    ):

        async def emit(ev):
            pass

        await hs.run(on_event=emit)

    assert hs.status == "ready"

    # Apply → persist workflow
    result = await hs.apply()
    workflow_id = result["workflow_id"]

    # Reload from DB to ensure serialization round-trip is clean
    wf = db.query(Workflow).filter(Workflow.id == workflow_id).first()
    assert wf is not None
    graph_json = json.loads(wf.graph_json)

    # Canonical v2 contract assertions
    assert graph_json["version"] == 2
    assert all("config" in node for node in graph_json["nodes"])
    assert all("data" not in node for node in graph_json["nodes"])

    # Engine execution (mock LLM)
    events = []

    async def on_event(event):
        events.append(event)

    with patch("backend.nodes.llm_node.LLMNode._get_chat_model") as mock_llm:
        mock_model = AsyncMock()
        mock_response = MagicMock()
        mock_response.content = "Hello from mocked LLM"
        mock_model.ainvoke.return_value = mock_response
        mock_llm.return_value = mock_model

        engine = ExecutionEngine()
        final_state = await engine.run(graph_json, user_input="hi", on_event=on_event)

    # Assertions
    event_types = [e["type"] for e in events]
    assert "workflow_start" in event_types
    assert "workflow_end" in event_types
    assert event_types[-1] == "workflow_end"

    workflow_end = [e for e in events if e["type"] == "workflow_end"][0]
    assert workflow_end["status"] == "completed"

    node_errors = [e for e in events if e["type"] == "node_end" and e.get("status") == "failed"]
    assert node_errors == []

    assert final_state["node_outputs"]["llm_1"]["text"] == "Hello from mocked LLM"


# ── test case 2: if/else subgraph ──

@pytest.mark.asyncio
async def test_harness_to_engine_if_else_subgraph(db: Session):
    """Harness builds Start → IfElse(true/false branches) → End.

    This is the most fragile area for Step 2 refactoring because validators.py
    and compiler.py both enforce cross-scope edge / subgraph rules.
    """
    db.add(
        Provider(
            type="openai",
            name="test",
            api_key_encrypted="enc",
            enabled=True,
            category="llm",
        )
    )
    db.commit()

    hs = create_harness_session(db, goal="build a branching workflow")
    hs.setup_tools(MagicMock())
    hs.init_lead_agent()

    decisions = [
        ProposeAction(action=AddNodeAction(node_type="start", node_id="start_1")),
        ProposeAction(action=AddNodeAction(node_type="if_else", node_id="if_1")),
        ProposeAction(action=AddNodeAction(node_type="end", node_id="end_1")),
        # Configure branches on if_else
        ProposeAction(
            action=UpdateNodeConfigAction(
                node_id="if_1",
                config={
                    "branches": [
                        {
                            "id": "true",
                            "condition": {
                                "left": "{{start_1.input}}",
                                "op": "eq",
                                "right": "test",
                            },
                            "outputField": "llm_true.text",
                        },
                        {
                            "id": "false",
                            "condition": None,
                            "outputField": "llm_false.text",
                        },
                    ]
                },
            )
        ),
        # Branch children
        ProposeAction(
            action=AddNodeAction(
                node_type="llm",
                node_id="llm_true",
                parent_id="if_1",
                config={"branchId": "true", "provider_id": 1},
            )
        ),
        ProposeAction(
            action=AddNodeAction(
                node_type="llm",
                node_id="llm_false",
                parent_id="if_1",
                config={"branchId": "false", "provider_id": 1},
            )
        ),
        # Top-level edges
        ProposeAction(action=AddEdgeAction(source="start_1", target="if_1")),
        ProposeAction(action=AddEdgeAction(source="if_1", target="end_1")),
        Finalize(reason="done"),
    ]

    with patch.object(
        hs.lead_agent, "decide", side_effect=_make_decision_sequence(decisions)
    ):

        async def emit(ev):
            pass

        await hs.run(on_event=emit)

    assert hs.status == "ready"

    # Apply
    result = await hs.apply()
    workflow_id = result["workflow_id"]

    # Verify DB round-trip
    wf = db.query(Workflow).filter(Workflow.id == workflow_id).first()
    assert wf is not None
    graph_json = json.loads(wf.graph_json)

    # Canonical v2 contract assertions
    assert graph_json["version"] == 2
    assert all("config" in node for node in graph_json["nodes"])
    assert all("data" not in node for node in graph_json["nodes"])

    true_child = next(n for n in graph_json["nodes"] if n["id"] == "llm_true")
    assert true_child["parentId"] == "if_1"
    assert true_child["branchId"] == "true"
    assert true_child["config"]["provider_id"] == 1

    # Engine execution (mock LLM)
    events = []

    async def on_event(event):
        events.append(event)

    with patch("backend.nodes.llm_node.LLMNode._get_chat_model") as mock_llm:
        mock_model = AsyncMock()
        mock_response = MagicMock()
        mock_response.content = "branch output"
        mock_model.ainvoke.return_value = mock_response
        mock_llm.return_value = mock_model

        engine = ExecutionEngine()
        final_state = await engine.run(
            graph_json, user_input="test", on_event=on_event
        )

    # Assertions
    event_types = [e["type"] for e in events]
    assert "workflow_start" in event_types
    assert "workflow_end" in event_types
    assert event_types[-1] == "workflow_end"

    workflow_end = [e for e in events if e["type"] == "workflow_end"][0]
    assert workflow_end["status"] == "completed"

    node_errors = [e for e in events if e["type"] == "node_end" and e.get("status") == "failed"]
    assert node_errors == []

    branch_events = [e for e in events if e["type"] == "branch_taken"]
    assert len(branch_events) == 1
    assert branch_events[0]["branch_id"] == "true"

    assert final_state["node_outputs"]["if_1"]["branchTaken"] == "true"
    assert final_state["node_outputs"]["if_1"]["result"] == "branch output"

    # Only the selected branch node should have executed
    node_ids = [e.get("node_id") for e in events if e["type"] in ("node_start", "node_end")]
    assert "llm_true" in node_ids
    assert "llm_false" not in node_ids
