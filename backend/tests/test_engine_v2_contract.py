import pytest

from backend.core.engine import ExecutionEngine
from backend.nodes.base import BaseNode
from backend.core.state import WorkflowState
from backend.nodes.registry import node_registry


class EchoNode(BaseNode):
    node_type = "echo_v2"

    async def execute(self, state: WorkflowState, **kwargs) -> WorkflowState:
        state.setdefault("node_outputs", {})
        state["node_outputs"][self.node_id] = {
            self.config.get("output_key", "text"): self.config.get("output_value", "ok")
        }
        return state


try:
    node_registry.register(EchoNode)
except KeyError:
    pass


@pytest.mark.asyncio
async def test_engine_runs_if_else_branch_from_v2_metadata():
    graph = {
        "version": 2,
        "nodes": [
            {"id": "start_1", "type": "start", "config": {}},
            {
                "id": "if_1",
                "type": "if_else",
                "config": {
                    "branches": [
                        {"id": "true", "condition": None, "outputField": "echo_true.text"}
                    ]
                },
            },
            {
                "id": "echo_true",
                "type": "echo_v2",
                "parentId": "if_1",
                "branchId": "true",
                "config": {"output_key": "text", "output_value": "yes"},
            },
            {"id": "end_1", "type": "end", "config": {}},
        ],
        "edges": [
            {"source": "start_1", "target": "if_1"},
            {"source": "if_1", "target": "end_1"},
        ],
    }

    state = await ExecutionEngine().run(graph, user_input="go")

    assert state["node_outputs"]["if_1"]["branchTaken"] == "true"
    assert state["node_outputs"]["if_1"]["result"] == "yes"


@pytest.mark.asyncio
async def test_engine_runs_iteration_from_v2_metadata():
    graph = {
        "version": 2,
        "nodes": [
            {"id": "start_1", "type": "start", "config": {"inputs": [{"name": "items", "type": "text"}]}},
            {
                "id": "iter_1",
                "type": "iteration",
                "config": {
                    "inputRef": "{{start_1.items}}",
                    "itemVar": "item",
                    "outputField": "echo_body.text",
                    "maxConcurrency": 1,
                },
            },
            {
                "id": "echo_body",
                "type": "echo_v2",
                "parentId": "iter_1",
                "config": {"output_key": "text", "output_value": "item-output"},
            },
            {"id": "end_1", "type": "end", "config": {}},
        ],
        "edges": [
            {"source": "start_1", "target": "iter_1"},
            {"source": "iter_1", "target": "end_1"},
        ],
    }

    state = await ExecutionEngine().run(graph, inputs={"items": ["a", "b"]})

    assert state["node_outputs"]["iter_1"]["results"] == ["item-output", "item-output"]
