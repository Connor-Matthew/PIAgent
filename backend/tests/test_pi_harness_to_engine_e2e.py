"""E2E tests: pi_harness draft → apply persists it → engine executes it.

These tests guard against divergence between harness validation and engine
compilation/execution, especially for control-flow subgraphs.
"""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from backend.core.engine import ExecutionEngine
from backend.pi_harness.session import create_harness_session


async def _noop(_) -> None:
    pass


async def _apply_ready_graph(db, graph: dict) -> tuple[str, dict]:
    session = create_harness_session(db, goal="engine parity")
    session.draft.load_snapshot(graph)
    session._status = "ready"
    result = await session.apply()
    return result["workflow_id"], result["graph"]


@pytest.mark.asyncio
async def test_pi_harness_to_engine_linear_workflow(db):
    graph = {
        "version": 2,
        "nodes": [
            {"id": "start_1", "type": "start", "config": {"inputs": []}},
            {"id": "llm_1", "type": "llm", "config": {"provider_id": 1}},
            {"id": "end_1", "type": "end", "config": {"outputs": []}},
        ],
        "edges": [
            {"id": "start_1-llm_1", "source": "start_1", "target": "llm_1"},
            {"id": "llm_1-end_1", "source": "llm_1", "target": "end_1"},
        ],
    }

    _, persisted_graph = await _apply_ready_graph(db, graph)

    with patch("backend.nodes.llm_node.LLMNode._get_chat_model") as mock_llm:
        model = AsyncMock()
        response = MagicMock()
        response.content = "Hello from mocked LLM"
        model.ainvoke.return_value = response
        mock_llm.return_value = model

        engine = ExecutionEngine()
        final_state = await engine.run(persisted_graph, user_input="hi", on_event=_noop)

    assert final_state["node_outputs"]["llm_1"]["text"] == "Hello from mocked LLM"


@pytest.mark.asyncio
async def test_pi_harness_to_engine_if_else_subgraph(db):
    graph = {
        "version": 2,
        "nodes": [
            {"id": "start_1", "type": "start", "config": {"inputs": []}},
            {
                "id": "if_1",
                "type": "if_else",
                "config": {
                    "branches": [
                        {"id": "true", "condition": {"left": "{{start_1.input}}", "op": "eq", "right": "test"}, "outputField": "llm_true.text"},
                        {"id": "false", "condition": None, "outputField": "llm_false.text"},
                    ]
                },
            },
            {"id": "llm_true", "type": "llm", "parentId": "if_1", "branchId": "true", "config": {"provider_id": 1}},
            {"id": "llm_false", "type": "llm", "parentId": "if_1", "branchId": "false", "config": {"provider_id": 1}},
            {"id": "end_1", "type": "end", "config": {"outputs": []}},
        ],
        "edges": [
            {"id": "start_1-if_1", "source": "start_1", "target": "if_1"},
            {"id": "if_1-end_1", "source": "if_1", "target": "end_1"},
        ],
    }

    _, persisted_graph = await _apply_ready_graph(db, graph)

    with patch("backend.nodes.llm_node.LLMNode._get_chat_model") as mock_llm:
        model = AsyncMock()
        response = MagicMock()
        response.content = "branch output"
        model.ainvoke.return_value = response
        mock_llm.return_value = model

        engine = ExecutionEngine()
        final_state = await engine.run(persisted_graph, user_input="test", on_event=_noop)

    assert "node_outputs" in final_state
