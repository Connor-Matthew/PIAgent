"""Write authoring tools for the ReAct builder agent."""

from __future__ import annotations

import json
from typing import Any

from langchain_core.tools import tool

from backend.harness.actions import AddEdgeAction, AddNodeAction, DeleteEdgeAction, DeleteNodeAction, UpdateNodeConfigAction
from backend.harness.builder import GraphBuilder
from backend.harness.react_tools.base import ToolContext, _json_compact
from backend.harness.validators import validate_graph


def _builder_snapshot_hash(builder: GraphBuilder) -> str:
    import hashlib
    payload = json.dumps(builder.snapshot(), sort_keys=True)
    return hashlib.sha256(payload.encode()).hexdigest()[:16]


def make_write_tools(ctx: ToolContext) -> list[Any]:
    """Build write LangChain tools bound to a ToolContext."""

    @tool
    def add_node(
        node_type: str,
        node_id: str | None = None,
        config: dict | None = None,
        parent_id: str | None = None,
    ) -> str:
        """Add a node to the workflow graph draft.

        Args:
            node_type: One of start, llm, rag, tts, end.
            node_id: Optional explicit ID (auto-generated if omitted).
            config: Node configuration dict matching the node's config schema.
            parent_id: Parent node id for nested nodes (if_else/iteration branches).
        """
        action = AddNodeAction(
            node_type=node_type,
            node_id=node_id,
            config=config or {},
            parent_id=parent_id,
        )
        try:
            ctx.builder.apply(action)
            snapshot = ctx.builder.snapshot()
            ctx.workspace.record_graph_update(snapshot)
            return _json_compact({
                "ok": True,
                "action": "add_node",
                "node_id": snapshot["nodes"][-1]["id"],
                "node_type": node_type,
                "node_count": len(snapshot["nodes"]),
            })
        except Exception as exc:
            return _json_compact({"ok": False, "action": "add_node", "error": str(exc)})

    @tool
    def update_node_config(node_id: str, config: dict) -> str:
        """Update configuration fields of an existing node.

        Args:
            node_id: ID of the node to update.
            config: Patch dict of configuration fields to merge.
        """
        action = UpdateNodeConfigAction(node_id=node_id, config=config)
        try:
            ctx.builder.apply(action)
            snapshot = ctx.builder.snapshot()
            ctx.workspace.record_graph_update(snapshot)
            return _json_compact({"ok": True, "action": "update_node_config", "node_id": node_id})
        except Exception as exc:
            return _json_compact({"ok": False, "action": "update_node_config", "error": str(exc)})

    @tool
    def delete_node(node_id: str) -> str:
        """Delete a node (and its children) from the graph draft.

        Args:
            node_id: ID of the node to delete.
        """
        action = DeleteNodeAction(node_id=node_id)
        try:
            ctx.builder.apply(action)
            snapshot = ctx.builder.snapshot()
            ctx.workspace.record_graph_update(snapshot)
            return _json_compact({"ok": True, "action": "delete_node", "node_id": node_id})
        except Exception as exc:
            return _json_compact({"ok": False, "action": "delete_node", "error": str(exc)})

    @tool
    def connect_nodes(source: str, target: str) -> str:
        """Add an edge between two existing nodes.

        Args:
            source: Source node ID.
            target: Target node ID.
        """
        action = AddEdgeAction(source=source, target=target)
        try:
            ctx.builder.apply(action)
            snapshot = ctx.builder.snapshot()
            ctx.workspace.record_graph_update(snapshot)
            return _json_compact({
                "ok": True,
                "action": "connect_nodes",
                "edge": f"{source} -> {target}",
                "edge_count": len(snapshot["edges"]),
            })
        except Exception as exc:
            return _json_compact({"ok": False, "action": "connect_nodes", "error": str(exc)})

    @tool
    def delete_edge(source: str, target: str) -> str:
        """Delete an edge between two nodes.

        Args:
            source: Source node ID.
            target: Target node ID.
        """
        action = DeleteEdgeAction(source=source, target=target)
        try:
            ctx.builder.apply(action)
            snapshot = ctx.builder.snapshot()
            ctx.workspace.record_graph_update(snapshot)
            return _json_compact({"ok": True, "action": "delete_edge", "edge": f"{source} -> {target}"})
        except Exception as exc:
            return _json_compact({"ok": False, "action": "delete_edge", "error": str(exc)})

    @tool
    def validate_graph() -> str:
        """Run deterministic validation on the current graph draft.

        Returns findings (errors and warnings). If errors exist, fix them before finalizing.
        """
        findings = validate_graph(ctx.builder.snapshot(), db=ctx.db)
        ctx.workspace.record_validation(findings)
        errors = [f for f in findings if f.severity == "error"]
        warnings = [f for f in findings if f.severity == "warning"]
        return _json_compact({
            "ok": len(errors) == 0,
            "errors": [{"code": f.code, "message": f.message, "node_id": f.node_id} for f in errors],
            "warnings": [{"code": f.code, "message": f.message, "node_id": f.node_id} for f in warnings],
        })

    @tool
    def finalize_graph() -> str:
        """Attempt to finalize the graph draft.

        Runs validation. If no errors, marks the session as ready for apply.
        If errors exist, returns them so the agent can fix them.
        """
        findings = validate_graph(ctx.builder.snapshot(), db=ctx.db)
        ctx.workspace.record_validation(findings)
        errors = [f for f in findings if f.severity == "error"]
        if errors:
            return _json_compact({
                "ok": False,
                "status": "needs_fix",
                "errors": [{"code": f.code, "message": f.message, "node_id": f.node_id} for f in errors],
            })
        return _json_compact({
            "ok": True,
            "status": "ready",
            "node_count": len(ctx.builder.snapshot().get("nodes", [])),
            "edge_count": len(ctx.builder.snapshot().get("edges", [])),
        })

    return [
        add_node,
        update_node_config,
        delete_node,
        connect_nodes,
        delete_edge,
        validate_graph,
        finalize_graph,
    ]
