"""PIAgent Harness v2 — GraphBuilder: mutable graph draft manipulated via GraphActions."""

from __future__ import annotations

import random
import uuid

from backend.harness.actions import BuilderError
from backend.harness.schemas import (
    AddEdgeAction,
    AddNodeAction,
    DeleteEdgeAction,
    DeleteNodeAction,
    GraphAction,
    UpdateNodeConfigAction,
)

# ───────────────────────────────────────────────
# Position helpers
# ───────────────────────────────────────────────

_GRID_SIZE = 180
_MARGIN = 100


def _next_position(existing_nodes: list[dict]) -> dict[str, float]:
    """Place a new node on a rough grid to avoid total overlap."""
    count = len(existing_nodes)
    cols = 3
    row = count // cols
    col = count % cols
    x = _MARGIN + col * _GRID_SIZE + random.randint(-20, 20)
    y = _MARGIN + row * _GRID_SIZE + random.randint(-20, 20)
    return {"x": float(x), "y": float(y)}


# ───────────────────────────────────────────────
# GraphBuilder
# ───────────────────────────────────────────────

class GraphBuilder:
    """Maintains a workflow graph draft (nodes + edges) and applies GraphActions."""

    def __init__(self) -> None:
        self._nodes: list[dict] = []
        self._edges: list[dict] = []

    # ── public API ──

    def apply(self, action: GraphAction) -> None:
        match action.kind:
            case "add_node":
                self._add_node(action)
            case "add_edge":
                self._add_edge(action)
            case "update_node_config":
                self._update_node_config(action)
            case "delete_node":
                self._delete_node(action)
            case "delete_edge":
                self._delete_edge(action)
            case _:
                raise BuilderError(f"Unsupported action kind: {action.kind}")

    def snapshot(self) -> dict:
        """Return a JSON-serialisable snapshot of the current graph."""
        return {
            "nodes": [dict(n) for n in self._nodes],
            "edges": [dict(e) for e in self._edges],
        }

    def from_snapshot(self, snapshot: dict) -> None:
        """Restore from a snapshot."""
        self._nodes = [dict(n) for n in snapshot.get("nodes", [])]
        self._edges = [dict(e) for e in snapshot.get("edges", [])]

    def node_ids(self) -> set[str]:
        return {n["id"] for n in self._nodes}

    def edge_ids(self) -> set[str]:
        return {e["id"] for e in self._edges}

    # ── action implementations ──

    def _add_node(self, action: AddNodeAction) -> None:
        node_id = action.node_id
        if not node_id:
            node_id = f"{action.node_type}_{uuid.uuid4().hex[:8]}"

        if node_id in self.node_ids():
            raise BuilderError(f"Node '{node_id}' already exists")

        pos = _next_position(self._nodes)
        node = {
            "id": node_id,
            "type": action.node_type,
            "position": pos,
            "data": dict(action.config),
        }
        self._nodes.append(node)

    def _add_edge(self, action: AddEdgeAction) -> None:
        if action.source not in self.node_ids():
            raise BuilderError(f"Edge source node '{action.source}' does not exist")
        if action.target not in self.node_ids():
            raise BuilderError(f"Edge target node '{action.target}' does not exist")

        edge_id = f"{action.source}-{action.target}"
        if edge_id in self.edge_ids():
            raise BuilderError(f"Edge '{edge_id}' already exists")

        self._edges.append({
            "id": edge_id,
            "source": action.source,
            "target": action.target,
        })

    def _update_node_config(self, action: UpdateNodeConfigAction) -> None:
        for node in self._nodes:
            if node["id"] == action.node_id:
                node["data"].update(action.config)
                return
        raise BuilderError(f"Node '{action.node_id}' not found for config update")

    def _delete_node(self, action: DeleteNodeAction) -> None:
        original_len = len(self._nodes)
        self._nodes = [n for n in self._nodes if n["id"] != action.node_id]
        if len(self._nodes) == original_len:
            raise BuilderError(f"Node '{action.node_id}' not found for deletion")
        # Cascade: remove incident edges
        self._edges = [
            e for e in self._edges
            if e["source"] != action.node_id and e["target"] != action.node_id
        ]

    def _delete_edge(self, action: DeleteEdgeAction) -> None:
        edge_id = f"{action.source}-{action.target}"
        original_len = len(self._edges)
        self._edges = [e for e in self._edges if e["id"] != edge_id]
        if len(self._edges) == original_len:
            raise BuilderError(f"Edge '{edge_id}' not found for deletion")
