import asyncio
import pytest
from backend.core.engine import ExecutionEngine
from backend.core.state import WorkflowState
from backend.nodes.base import BaseNode
from backend.nodes.registry import node_registry
from backend.nodes.iteration_node import IterationNode


class DelayEchoNode(BaseNode):
    node_type = "delay_echo"

    async def execute(self, state: WorkflowState, **kwargs) -> WorkflowState:
        delay = self.config.get("delay", 0)
        if delay:
            await asyncio.sleep(delay)
        value = self.config.get("output_value", "ok")
        state.setdefault("node_outputs", {})
        state["node_outputs"][self.node_id] = {"text": value}
        return state


class ConditionalFailNode(BaseNode):
    node_type = "conditional_fail"
    _executed_indices: set[int] = set()

    async def execute(self, state: WorkflowState, **kwargs) -> WorkflowState:
        idx = state.get("_iter_context", {}).get("index", -1)
        ConditionalFailNode._executed_indices.add(idx)
        fail_at = self.config.get("fail_at_index")
        if idx == fail_at:
            raise RuntimeError(f"fail at {fail_at}")
        value = self.config.get("output_value", "ok")
        state.setdefault("node_outputs", {})
        state["node_outputs"][self.node_id] = {"text": value}
        return state


class BarrierFailNode(BaseNode):
    node_type = "barrier_fail"
    _gate: asyncio.Event | None = None
    _executed_indices: set[int] = set()

    async def execute(self, state: WorkflowState, **kwargs) -> WorkflowState:
        idx = state.get("_iter_context", {}).get("index", -1)
        await asyncio.sleep(0)  # yield so all siblings are scheduled
        if idx == 1:
            raise RuntimeError("fail at 1")
        if BarrierFailNode._gate is not None:
            await BarrierFailNode._gate.wait()  # hangs forever; cancelled on fail_fast
        BarrierFailNode._executed_indices.add(idx)
        state.setdefault("node_outputs", {})
        state["node_outputs"][self.node_id] = {"text": "ok"}
        return state


class CountingNode(BaseNode):
    node_type = "counting"
    _counter: list[int] = [0]
    _max_seen: list[int] = [0]

    async def execute(self, state: WorkflowState, **kwargs) -> WorkflowState:
        CountingNode._counter[0] += 1
        CountingNode._max_seen[0] = max(CountingNode._max_seen[0], CountingNode._counter[0])
        await asyncio.sleep(0.05)
        CountingNode._counter[0] -= 1
        state.setdefault("node_outputs", {})
        state["node_outputs"][self.node_id] = {"text": "ok"}
        return state


# Register nodes for tests
for _cls in (IterationNode, DelayEchoNode, ConditionalFailNode, CountingNode, BarrierFailNode):
    try:
        node_registry.register(_cls)
    except KeyError:
        pass


@pytest.mark.asyncio
async def test_iteration_parallel_preserves_order():
    """Even if items finish out of order, results must stay in input order."""
    graph_json = {
        "nodes": [
            {"id": "start_1", "type": "start", "data": {}},
            {
                "id": "iter_1",
                "type": "iteration",
                "data": {
                    "inputRef": "{{start_1.items}}",
                    "maxConcurrency": 3,
                    "outputField": "delay_1.text",
                },
            },
            {
                "id": "delay_1",
                "type": "delay_echo",
                "data": {"parentId": "iter_1"},
            },
            {"id": "end_1", "type": "end", "data": {}},
        ],
        "edges": [
            {"source": "start_1", "target": "iter_1"},
            {"source": "iter_1", "target": "end_1"},
        ],
    }
    engine = ExecutionEngine()
    # Use inputs so that StartNode stores them in node_outputs
    result = await engine.run(
        graph_json,
        user_input="",
        inputs={"items": ["a", "b", "c"]},
    )

    assert result["node_outputs"]["iter_1"]["results"] == ["ok", "ok", "ok"]


@pytest.mark.asyncio
async def test_iteration_fail_fast_cancels_siblings():
    """fail_fast: first error cancels remaining concurrent tasks.

    Siblings yield with asyncio.sleep(0) and then hang on an Event
    that is never set. When task1 fails, gather cancels the hung
    siblings before they reach the add() line.
    """
    BarrierFailNode._gate = asyncio.Event()  # never set
    BarrierFailNode._executed_indices.clear()

    graph_json = {
        "nodes": [
            {"id": "start_1", "type": "start", "data": {}},
            {
                "id": "iter_1",
                "type": "iteration",
                "data": {
                    "inputRef": "{{start_1.items}}",
                    "maxConcurrency": 3,
                    "errorStrategy": "fail_fast",
                    "outputField": "barrier_1.text",
                },
            },
            {
                "id": "barrier_1",
                "type": "barrier_fail",
                "data": {"parentId": "iter_1"},
            },
            {"id": "end_1", "type": "end", "data": {}},
        ],
        "edges": [
            {"source": "start_1", "target": "iter_1"},
            {"source": "iter_1", "target": "end_1"},
        ],
    }
    engine = ExecutionEngine()
    with pytest.raises(RuntimeError, match="fail at 1"):
        await engine.run(graph_json, inputs={"items": [1, 2, 3]})

    # Cancelled tasks never reach the add() line.
    assert BarrierFailNode._executed_indices == set()


@pytest.mark.asyncio
async def test_iteration_continue_records_errors():
    """continue: failed items record errors; siblings keep running."""
    ConditionalFailNode._executed_indices.clear()

    graph_json = {
        "nodes": [
            {"id": "start_1", "type": "start", "data": {}},
            {
                "id": "iter_1",
                "type": "iteration",
                "data": {
                    "inputRef": "{{start_1.items}}",
                    "maxConcurrency": 3,
                    "errorStrategy": "continue",
                    "outputField": "fail_1.text",
                },
            },
            {
                "id": "fail_1",
                "type": "conditional_fail",
                "data": {"parentId": "iter_1", "fail_at_index": 1},
            },
            {"id": "end_1", "type": "end", "data": {}},
        ],
        "edges": [
            {"source": "start_1", "target": "iter_1"},
            {"source": "iter_1", "target": "end_1"},
        ],
    }
    engine = ExecutionEngine()
    result = await engine.run(graph_json, inputs={"items": [1, 2, 3]})

    # All three should have been attempted
    assert ConditionalFailNode._executed_indices == {0, 1, 2}

    assert result["node_outputs"]["iter_1"]["results"] == ["ok", None, "ok"]
    assert result["node_outputs"]["iter_1"]["errors"] == [{"index": 1, "error": "fail at 1"}]


@pytest.mark.asyncio
async def test_iteration_concurrency_bounded():
    """Verify that maxConcurrency actually limits concurrent body executions."""
    CountingNode._counter[0] = 0
    CountingNode._max_seen[0] = 0

    graph_json = {
        "nodes": [
            {"id": "start_1", "type": "start", "data": {}},
            {
                "id": "iter_1",
                "type": "iteration",
                "data": {
                    "inputRef": "{{start_1.items}}",
                    "maxConcurrency": 2,
                    "outputField": "count_1.text",
                },
            },
            {
                "id": "count_1",
                "type": "counting",
                "data": {"parentId": "iter_1"},
            },
            {"id": "end_1", "type": "end", "data": {}},
        ],
        "edges": [
            {"source": "start_1", "target": "iter_1"},
            {"source": "iter_1", "target": "end_1"},
        ],
    }
    engine = ExecutionEngine()
    await engine.run(graph_json, inputs={"items": [1, 2, 3]})

    assert CountingNode._max_seen[0] == 2
