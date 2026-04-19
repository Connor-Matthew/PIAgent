import asyncio
import json
import time
from typing import Callable, Awaitable, Any

from backend.core.compiler import GraphCompiler
from backend.core.state import WorkflowState
from backend.core.template import REF_RE, resolve_reference


class ExecutionEngine:
    def __init__(self):
        self.compiler = GraphCompiler()

    async def _emit(
        self, on_event: Callable[[dict], Awaitable[None]] | None, event: dict
    ) -> None:
        if on_event is not None:
            await on_event(event)

    async def run(
        self,
        graph_json: dict,
        user_input: str = "",
        inputs: dict[str, Any] | None = None,
        on_event: Callable[[dict], Awaitable[None]] | None = None,
    ) -> WorkflowState:
        """Execute a workflow graph and emit events for each node.

        Event types emitted:
        - workflow_start: Emitted before the first node begins execution.
        - node_start / node_end: Emitted around each node's execution.
        - branch_taken: Emitted when an if_else node selects a branch.
        - iteration_item_start / iteration_item_end: Emitted around each iteration item.
        - workflow_end: Emitted after all nodes finish or when a node fails.
        """
        compiled = self.compiler.compile(graph_json)
        state: WorkflowState = {
            "input": user_input,
            "inputs": inputs or {},
            "messages": [],
            "context": "",
            "llm_output": "",
            "audio_url": "",
            "node_outputs": {},
        }

        self._user_input = user_input
        workflow_start = time.time()

        await self._emit(on_event, {"type": "workflow_start"})

        try:
            await self._run_scope(
                compiled=compiled,
                scope_nodes=compiled.top_level_order,
                state=state,
                on_event=on_event,
                parent_id=None,
            )
        except Exception:
            total_duration = round(time.time() - workflow_start, 3)
            await self._emit(on_event, {
                "type": "workflow_end",
                "status": "failed",
                "duration": total_duration,
                "answer": state.get("answer", ""),
                "outputs": state.get("outputs", {}),
            })
            raise

        total_duration = round(time.time() - workflow_start, 3)

        await self._emit(on_event, {
            "type": "workflow_end",
            "status": "completed",
            "duration": total_duration,
            "answer": state.get("answer", ""),
            "outputs": state.get("outputs", {}),
        })

        return state

    async def _run_scope(
        self,
        compiled,
        scope_nodes: list[str],
        state: WorkflowState,
        on_event: Callable[[dict], Awaitable[None]] | None,
        parent_id: str | None,
        iteration_index: int | None = None,
    ) -> None:
        """Execute a sequence of nodes within a scope (top-level or subgraph)."""
        for node_id in scope_nodes:
            node_def = compiled.node_defs[node_id]
            node_type = node_def["type"]

            if node_type == "if_else":
                await self._run_if_else(compiled, node_id, state, on_event, iteration_index)
            elif node_type == "iteration":
                await self._run_iteration(compiled, node_id, state, on_event)
            else:
                node = compiled.nodes[node_id]
                await self._run_single(node, node_id, node_type, state, on_event, iteration_index)

    async def _run_single(
        self,
        node,
        node_id: str,
        node_type: str,
        state: WorkflowState,
        on_event: Callable[[dict], Awaitable[None]] | None,
        iteration_index: int | None = None,
    ) -> None:
        event: dict = {
            "type": "node_start",
            "node_id": node_id,
            "node_type": node_type,
            "status": "running",
        }
        if iteration_index is not None:
            event["iteration_index"] = iteration_index
        await self._emit(on_event, event)

        node_start = time.time()
        try:
            state = await node.execute(state, user_input=self._user_input, on_event=on_event)
        except Exception as exc:
            duration = round(time.time() - node_start, 3)
            event = {
                "type": "node_end",
                "node_id": node_id,
                "node_type": node_type,
                "status": "failed",
                "duration": duration,
                "error": str(exc),
            }
            if iteration_index is not None:
                event["iteration_index"] = iteration_index
            await self._emit(on_event, event)
            raise
        else:
            duration = round(time.time() - node_start, 3)
            event = {
                "type": "node_end",
                "node_id": node_id,
                "node_type": node_type,
                "status": "completed",
                "duration": duration,
                "output": state.get("node_outputs", {}).get(node_id, {}),
            }
            if iteration_index is not None:
                event["iteration_index"] = iteration_index
            await self._emit(on_event, event)

    async def _run_if_else(
        self,
        compiled,
        if_else_id: str,
        state: WorkflowState,
        on_event: Callable[[dict], Awaitable[None]] | None,
        iteration_index: int | None = None,
    ) -> None:
        from backend.nodes.if_else_node import IfElseNode

        branches = compiled.node_configs.get(if_else_id, {}).get("branches", [])

        await self._emit(on_event, {
            "type": "node_start",
            "node_id": if_else_id,
            "node_type": "if_else",
            "status": "running",
        })

        selected_branch = None
        for branch in branches:
            condition = branch.get("condition")
            if condition is None:
                selected_branch = branch
                break
            result = IfElseNode.evaluate_condition(condition, state)
            if result:
                selected_branch = branch
                break

        branch_id = selected_branch["id"] if selected_branch else None
        condition_result = bool(selected_branch and selected_branch.get("condition") is not None)

        await self._emit(on_event, {
            "type": "branch_taken",
            "node_id": if_else_id,
            "branch_id": branch_id,
            "condition_result": condition_result,
        })

        if selected_branch:
            children = compiled.children_by_parent.get(if_else_id, [])
            branch_children = [
                cid
                for cid in children
                if compiled.branch_by_node.get(cid) == branch_id
            ]

            branch_state = {
                **state,
                "node_outputs": dict(state.get("node_outputs", {})),
            }
            await self._run_scope(compiled, branch_children, branch_state, on_event, if_else_id, iteration_index)

            output_field = selected_branch.get("outputField")
            result = None
            if output_field:
                result = self._extract_output_field(branch_state, output_field)

            node_outputs = state.setdefault("node_outputs", {})
            node_outputs[if_else_id] = {
                "branchTaken": branch_id,
                "result": result,
            }
        else:
            node_outputs = state.setdefault("node_outputs", {})
            node_outputs[if_else_id] = {
                "branchTaken": None,
                "result": None,
            }

        await self._emit(on_event, {
            "type": "node_end",
            "node_id": if_else_id,
            "node_type": "if_else",
            "status": "completed",
            "output": state["node_outputs"][if_else_id],
        })

    async def _run_iteration(
        self,
        compiled,
        iter_id: str,
        state: WorkflowState,
        on_event: Callable[[dict], Awaitable[None]] | None,
    ) -> None:
        config = compiled.node_configs.get(iter_id, {})
        input_ref = config.get("inputRef", "")
        item_var = config.get("itemVar", "item")
        index_var = config.get("indexVar", "index")
        output_field = config.get("outputField", "")
        error_strategy = config.get("errorStrategy", "fail_fast")
        max_concurrency = config.get("maxConcurrency", 5)

        await self._emit(on_event, {
            "type": "node_start",
            "node_id": iter_id,
            "node_type": "iteration",
            "status": "running",
        })

        # Resolve inputRef
        if REF_RE.fullmatch(input_ref):
            items = resolve_reference(input_ref, state)
        else:
            items = input_ref

        if not isinstance(items, list):
            raise ValueError(
                f"Iteration inputRef must resolve to a list, got {type(items).__name__}: {items!r}"
            )

        children = compiled.children_by_parent.get(iter_id, [])

        results: list[Any] = [None] * len(items)
        errors: list[dict] = []

        if max_concurrency <= 1:
            # Serial execution (M3)
            for i, item in enumerate(items):
                await self._emit(on_event, {
                    "type": "iteration_item_start",
                    "node_id": iter_id,
                    "index": i,
                    "total": len(items),
                })

                try:
                    child_state = await self._run_iter_item(
                        i, item, children, state, on_event, compiled, iter_id, item_var, index_var
                    )
                    results[i] = self._extract_output_field(child_state, output_field)
                    await self._emit(on_event, {
                        "type": "iteration_item_end",
                        "node_id": iter_id,
                        "index": i,
                        "status": "completed",
                    })
                except Exception as exc:
                    await self._emit(on_event, {
                        "type": "iteration_item_end",
                        "node_id": iter_id,
                        "index": i,
                        "status": "failed",
                        "error": str(exc),
                    })
                    if error_strategy == "fail_fast":
                        raise
                    errors.append({"index": i, "error": str(exc)})
                    if error_strategy in ("continue", "ignore_error_output"):
                        results[i] = None
        else:
            # Concurrent execution (M4)
            semaphore = asyncio.Semaphore(max_concurrency)

            async def _task(i: int, item: Any):
                async with semaphore:
                    await self._emit(on_event, {
                        "type": "iteration_item_start",
                        "node_id": iter_id,
                        "index": i,
                        "total": len(items),
                    })
                    try:
                        child_state = await self._run_iter_item(
                            i, item, children, state, on_event, compiled, iter_id, item_var, index_var
                        )
                        results[i] = self._extract_output_field(child_state, output_field)
                        await self._emit(on_event, {
                            "type": "iteration_item_end",
                            "node_id": iter_id,
                            "index": i,
                            "status": "completed",
                        })
                    except Exception as exc:
                        await self._emit(on_event, {
                            "type": "iteration_item_end",
                            "node_id": iter_id,
                            "index": i,
                            "status": "failed",
                            "error": str(exc),
                        })
                        raise

            if error_strategy == "fail_fast":
                tasks = [_task(i, item) for i, item in enumerate(items)]
                await asyncio.gather(*tasks)
            else:
                # continue / ignore_error_output: swallow exceptions so siblings keep running
                tasks = [_task(i, item) for i, item in enumerate(items)]
                task_results = await asyncio.gather(*tasks, return_exceptions=True)
                for i, res in enumerate(task_results):
                    if isinstance(res, Exception):
                        errors.append({"index": i, "error": str(res)})
                        results[i] = None

        node_outputs = state.setdefault("node_outputs", {})
        iter_output: dict[str, Any] = {"results": results}
        if error_strategy != "ignore_error_output":
            iter_output["errors"] = errors
        node_outputs[iter_id] = iter_output

        await self._emit(on_event, {
            "type": "node_end",
            "node_id": iter_id,
            "node_type": "iteration",
            "status": "completed",
            "output": node_outputs[iter_id],
        })

    async def _run_iter_item(
        self,
        index: int,
        item: Any,
        children: list[str],
        parent_state: WorkflowState,
        on_event: Callable[[dict], Awaitable[None]] | None,
        compiled,
        iter_id: str,
        item_var: str,
        index_var: str,
    ) -> WorkflowState:
        child_state: WorkflowState = {
            **parent_state,
            "node_outputs": dict(parent_state.get("node_outputs", {})),
            "input": self._coerce_item_to_input(item),
            "_iter_context": {
                "item": item,
                "index": index,
                "itemVar": item_var,
                "indexVar": index_var,
            },
        }
        await self._run_scope(
            compiled=compiled,
            scope_nodes=children,
            state=child_state,
            on_event=on_event,
            parent_id=iter_id,
            iteration_index=index,
        )
        return child_state

    @staticmethod
    def _coerce_item_to_input(item: Any) -> str:
        if isinstance(item, str):
            return item
        if isinstance(item, (int, float)):
            return str(item)
        if isinstance(item, dict):
            return json.dumps(item, ensure_ascii=False)
        return str(item)

    @staticmethod
    def _extract_output_field(state: WorkflowState, output_field: str) -> Any:
        if not output_field:
            return None
        parts = output_field.split(".")
        if len(parts) == 2:
            node_id, field = parts
            return state.get("node_outputs", {}).get(node_id, {}).get(field)
        return None
