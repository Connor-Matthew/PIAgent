"""PIAgent Harness v2 — GraphAction primitives.

Models live in schemas.py (because Decision references GraphAction).
This module re-exports them for convenience and adds action helpers.
"""

from backend.harness.schemas import (
    AddEdgeAction,
    AddNodeAction,
    DeleteEdgeAction,
    DeleteNodeAction,
    GraphAction,
    UpdateNodeConfigAction,
)

__all__ = [
    "AddEdgeAction",
    "AddNodeAction",
    "DeleteEdgeAction",
    "DeleteNodeAction",
    "GraphAction",
    "UpdateNodeConfigAction",
    "action_summary",
    "BuilderError",
]


class BuilderError(Exception):
    """Raised when a GraphAction cannot be applied to the current graph draft."""

    pass


def action_summary(action: GraphAction) -> str:
    """Human-readable one-liner for a GraphAction."""
    match action.kind:
        case "add_node":
            nid = action.node_id or "(auto)"
            return f"add_node {action.node_type} [{nid}]"
        case "add_edge":
            return f"add_edge {action.source} -> {action.target}"
        case "update_node_config":
            keys = ", ".join(action.config.keys())
            return f"update_node_config {action.node_id} ({keys})"
        case "delete_node":
            return f"delete_node {action.node_id}"
        case "delete_edge":
            return f"delete_edge {action.source} -> {action.target}"
    return "unknown_action"
