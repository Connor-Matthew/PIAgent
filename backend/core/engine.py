import time
from typing import Callable, Awaitable

from backend.core.compiler import GraphCompiler
from backend.core.state import WorkflowState
from backend.nodes.registry import node_registry


class ExecutionEngine:
    def __init__(self):
        self.compiler = GraphCompiler()

    async def run(
        self,
        graph_json: dict,
        user_input: str,
        on_event: Callable[[dict], Awaitable[None]] | None = None,
    ) -> WorkflowState:
        """Execute a workflow graph and emit events for each node.

        Event types emitted:
        - workflow_start: Emitted before the first node begins execution.
        - node_start: Emitted before a node begins execution. Contains node_id,
          node_type, and status.
        - node_end: Emitted after a node finishes execution. Contains node_id,
          node_type, status ("completed" or "failed"), duration (seconds),
          output, and error (if failed).
        - workflow_end: Emitted after all nodes finish or when a node fails.
          Contains status ("completed" or "failed") and duration.
        """

        order = self.compiler.topological_sort(graph_json)
        node_map = {n["id"]: n for n in graph_json["nodes"]}

        # Initialize state
        state: WorkflowState = {
            "input": user_input,
            "messages": [],
            "context": "",
            "llm_output": "",
            "audio_url": "",
            "node_outputs": {},
        }

        workflow_start = time.time()

        if on_event:
            await on_event({
                "type": "workflow_start",
            })

        # Nodes mutate state in-place and return it
        for node_id in order:
            node_def = node_map[node_id]
            node_cls = node_registry.get(node_def["type"])
            config = node_def.get("data", {})
            config["id"] = node_def["id"]
            node_instance = node_cls(config=config)

            # Emit node_start
            if on_event:
                await on_event({
                    "type": "node_start",
                    "node_id": node_id,
                    "node_type": node_def["type"],
                    "status": "running",
                })

            node_start = time.time()
            duration = 0.0
            try:
                state = await node_instance.execute(state, user_input=user_input)
            except Exception as exc:
                duration = round(time.time() - node_start, 3)
                if on_event:
                    await on_event({
                        "type": "node_end",
                        "node_id": node_id,
                        "node_type": node_def["type"],
                        "status": "failed",
                        "duration": duration,
                        "error": str(exc),
                    })
                    await on_event({
                        "type": "workflow_end",
                        "status": "failed",
                        "duration": round(time.time() - workflow_start, 3),
                    })
                raise
            else:
                duration = round(time.time() - node_start, 3)
                if on_event:
                    await on_event({
                        "type": "node_end",
                        "node_id": node_id,
                        "node_type": node_def["type"],
                        "status": "completed",
                        "duration": duration,
                        "output": state.get("node_outputs", {}).get(node_id, {}),
                    })

        total_duration = round(time.time() - workflow_start, 3)

        if on_event:
            await on_event({
                "type": "workflow_end",
                "status": "completed",
                "duration": total_duration,
            })

        return state
