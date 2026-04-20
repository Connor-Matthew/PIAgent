from __future__ import annotations

import random
import uuid

from backend.core.graph_schema import dump_graph, load_graph

_GRID_SIZE = 180
_MARGIN = 100


def _next_position(existing_nodes: list[dict]) -> dict[str, float]:
    count = len(existing_nodes)
    cols = 3
    row = count // cols
    col = count % cols
    x = _MARGIN + col * _GRID_SIZE + random.randint(-20, 20)
    y = _MARGIN + row * _GRID_SIZE + random.randint(-20, 20)
    return {"x": float(x), "y": float(y)}


class DraftError(Exception):
    """Raised when the workflow graph draft cannot apply a requested mutation."""


class WorkflowGraphDraft:
    """Mutable workflow graph draft for the new pi_harness runtime."""

    def __init__(self, snapshot: dict | None = None):
        self._nodes: list[dict] = []
        self._edges: list[dict] = []
        if snapshot is not None:
            self.load_snapshot(snapshot)

    def snapshot(self) -> dict:
        return dump_graph(
            load_graph(
                {
                    "version": 2,
                    "nodes": [dict(node) for node in self._nodes],
                    "edges": [dict(edge) for edge in self._edges],
                }
            )
        )

    def load_snapshot(self, snapshot: dict) -> None:
        graph = dump_graph(load_graph(snapshot))
        self._nodes = [dict(node) for node in graph.get("nodes", [])]
        self._edges = [dict(edge) for edge in graph.get("edges", [])]

    def node_ids(self) -> set[str]:
        return {node["id"] for node in self._nodes}

    def edge_ids(self) -> set[str]:
        return {edge["id"] for edge in self._edges}

    def add_node(
        self,
        *,
        node_type: str,
        config: dict | None = None,
        node_id: str | None = None,
        parent_id: str | None = None,
        branch_id: str | None = None,
    ) -> dict:
        actual_node_id = node_id or f"{node_type}_{uuid.uuid4().hex[:8]}"
        if actual_node_id in self.node_ids():
            raise DraftError(f"Node '{actual_node_id}' already exists")

        node_config = dict(config or {})
        inline_branch_id = node_config.pop("branchId", None)
        node = {
            "id": actual_node_id,
            "type": node_type,
            "position": _next_position(self._nodes),
            "config": node_config,
        }
        if parent_id:
            node["parentId"] = parent_id
        effective_branch_id = branch_id or inline_branch_id
        if isinstance(effective_branch_id, str):
            node["branchId"] = effective_branch_id

        self._nodes.append(node)
        return dict(node)

    def connect_nodes(
        self,
        *,
        from_id: str,
        to_id: str,
        source_handle: str | None = None,
    ) -> dict:
        if from_id not in self.node_ids():
            raise DraftError(f"Edge source node '{from_id}' does not exist")
        if to_id not in self.node_ids():
            raise DraftError(f"Edge target node '{to_id}' does not exist")

        edge_id = f"{from_id}-{to_id}"
        if edge_id in self.edge_ids():
            raise DraftError(f"Edge '{edge_id}' already exists")

        edge = {
            "id": edge_id,
            "source": from_id,
            "target": to_id,
        }
        if source_handle:
            edge["sourceHandle"] = source_handle
        self._edges.append(edge)
        return dict(edge)

    def patch_node_config(self, *, node_id: str, fields: dict) -> dict:
        for node in self._nodes:
            if node["id"] != node_id:
                continue

            patch = dict(fields)
            if "parentId" in patch:
                node["parentId"] = patch.pop("parentId")
            if "branchId" in patch:
                node["branchId"] = patch.pop("branchId")
            node.setdefault("config", {}).update(patch)
            return dict(node)
        raise DraftError(f"Node '{node_id}' not found for config update")

    def remove_node(self, *, node_id: str) -> None:
        node_ids_to_remove = {
            node["id"]
            for node in self._nodes
            if node["id"] == node_id or node.get("parentId") == node_id
        }
        if not node_ids_to_remove:
            raise DraftError(f"Node '{node_id}' not found for deletion")

        self._nodes = [node for node in self._nodes if node["id"] not in node_ids_to_remove]
        self._edges = [
            edge
            for edge in self._edges
            if edge["source"] not in node_ids_to_remove and edge["target"] not in node_ids_to_remove
        ]

    def remove_edge(self, *, from_id: str, to_id: str) -> None:
        edge_id = f"{from_id}-{to_id}"
        original_len = len(self._edges)
        self._edges = [edge for edge in self._edges if edge["id"] != edge_id]
        if len(self._edges) == original_len:
            raise DraftError(f"Edge '{edge_id}' not found for deletion")

