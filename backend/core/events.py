from __future__ import annotations

from typing import Any, Literal


def _with_scope(
    event: dict[str, Any],
    *,
    scope_id: str | None = None,
    iteration_index: int | None = None,
) -> dict[str, Any]:
    if scope_id is not None:
        event["scope_id"] = scope_id
    if iteration_index is not None:
        event["iteration_index"] = iteration_index
    return event


def workflow_start() -> dict[str, Any]:
    return {"type": "workflow_start"}


def node_start(
    *,
    node_id: str,
    node_type: str,
    scope_id: str | None = None,
    iteration_index: int | None = None,
) -> dict[str, Any]:
    return _with_scope(
        {
            "type": "node_start",
            "node_id": node_id,
            "node_type": node_type,
            "status": "running",
        },
        scope_id=scope_id,
        iteration_index=iteration_index,
    )


def node_end(
    *,
    node_id: str,
    node_type: str,
    status: Literal["completed", "failed"],
    duration: float | None = None,
    output: dict[str, Any] | None = None,
    error: str | None = None,
    scope_id: str | None = None,
    iteration_index: int | None = None,
) -> dict[str, Any]:
    event: dict[str, Any] = {
        "type": "node_end",
        "node_id": node_id,
        "node_type": node_type,
        "status": status,
    }
    if duration is not None:
        event["duration"] = duration
    if output is not None:
        event["output"] = output
    if error is not None:
        event["error"] = error
    return _with_scope(event, scope_id=scope_id, iteration_index=iteration_index)


def workflow_end(
    *,
    status: Literal["completed", "failed", "cancelled"],
    duration: float,
    answer: str = "",
    outputs: dict[str, Any] | None = None,
    message: str | None = None,
) -> dict[str, Any]:
    event: dict[str, Any] = {
        "type": "workflow_end",
        "status": status,
        "duration": duration,
        "answer": answer,
        "outputs": outputs or {},
    }
    if message:
        event["message"] = message
    return event


def branch_taken(*, node_id: str, branch_id: str | None, condition_result: bool) -> dict[str, Any]:
    return {
        "type": "branch_taken",
        "node_id": node_id,
        "branch_id": branch_id,
        "condition_result": condition_result,
    }
