"""Pure-function graph structural rules shared between harness validators and engine compiler."""

from __future__ import annotations

from collections import defaultdict, deque
from dataclasses import dataclass
from typing import Literal

from backend.core.graph_schema import get_node_parent_id


@dataclass(frozen=True)
class Violation:
    code: str
    message: str
    node_id: str | None = None
    severity: Literal["error", "warning"] = "error"


def _get_parent_id(node_def: dict) -> str | None:
    return get_node_parent_id(node_def)


def check_parent_id_existence(nodes: list[dict]) -> list[Violation]:
    violations: list[Violation] = []
    node_ids = {n["id"] for n in nodes}
    for node_def in nodes:
        pid = _get_parent_id(node_def)
        if pid and pid not in node_ids:
            violations.append(
                Violation(
                    code="invalid_parent_id",
                    message=f"Node '{node_def['id']}' has parentId '{pid}' which does not exist in the graph",
                    node_id=node_def["id"],
                )
            )
    return violations


def check_start_end_no_parent(nodes: list[dict]) -> list[Violation]:
    violations: list[Violation] = []
    for node_def in nodes:
        if node_def.get("type") in ("start", "end"):
            pid = _get_parent_id(node_def)
            if pid:
                violations.append(
                    Violation(
                        code="start_end_with_parent",
                        message=f"Node '{node_def['id']}' of type '{node_def['type']}' cannot have a parentId",
                        node_id=node_def["id"],
                    )
                )
    return violations


def check_cross_scope_edges(nodes: list[dict], edges: list[dict]) -> list[Violation]:
    violations: list[Violation] = []
    node_by_id = {n["id"]: n for n in nodes}
    for edge in edges:
        source_id = edge.get("source", "")
        target_id = edge.get("target", "")
        if source_id not in node_by_id or target_id not in node_by_id:
            continue
        s = node_by_id[source_id]
        t = node_by_id[target_id]
        s_parent = _get_parent_id(s)
        t_parent = _get_parent_id(t)

        if s_parent == t_parent:
            continue
        if t_parent == source_id:
            continue
        if s_parent == target_id:
            continue

        violations.append(
            Violation(
                code="cross_scope_edge",
                message=(
                    f"Invalid cross-scope edge: {source_id} -> {target_id}. "
                    f"Edges must connect nodes within the same parent scope, "
                    f"or connect a parent node directly to/from its child."
                ),
                node_id=source_id,
            )
        )
    return violations


def check_subgraph_acyclicity(nodes: list[dict], edges: list[dict]) -> list[Violation]:
    violations: list[Violation] = []
    parent_ids = {_get_parent_id(n) for n in nodes if _get_parent_id(n)}
    for pid in parent_ids:
        child_ids = {n["id"] for n in nodes if _get_parent_id(n) == pid}
        internal_edges = [
            e for e in edges if e.get("source") in child_ids and e.get("target") in child_ids
        ]

        in_degree = defaultdict(int)
        adj = defaultdict(list)
        for e in internal_edges:
            adj[e["source"]].append(e["target"])
            in_degree[e["target"]] += 1

        queue = deque(n for n in child_ids if in_degree[n] == 0)
        visited = 0
        while queue:
            node = queue.popleft()
            visited += 1
            for neighbor in adj[node]:
                in_degree[neighbor] -= 1
                if in_degree[neighbor] == 0:
                    queue.append(neighbor)

        if visited != len(child_ids):
            violations.append(
                Violation(
                    code="subgraph_cycle",
                    message=f"Subgraph under parent '{pid}' contains a cycle",
                    node_id=pid,
                )
            )
    return violations


def check_subgraph_connectivity(nodes: list[dict], edges: list[dict]) -> list[Violation]:
    violations: list[Violation] = []
    parent_ids = {_get_parent_id(n) for n in nodes if _get_parent_id(n)}
    for pid in parent_ids:
        child_ids = {n["id"] for n in nodes if _get_parent_id(n) == pid}
        internal_edges = [
            e for e in edges if e.get("source") in child_ids and e.get("target") in child_ids
        ]

        has_incoming = set()
        for e in internal_edges:
            has_incoming.add(e["target"])

        entry_nodes = child_ids - has_incoming
        if not entry_nodes:
            violations.append(
                Violation(
                    code="subgraph_no_entry",
                    message=f"Subgraph under parent '{pid}' has no entry node",
                    node_id=pid,
                )
            )
    return violations


def check_global_acyclicity(nodes: list[dict], edges: list[dict]) -> list[Violation]:
    violations: list[Violation] = []
    node_ids = {n["id"] for n in nodes}
    if not node_ids:
        return violations

    node_by_id = {n["id"]: n for n in nodes}
    in_degree = defaultdict(int)
    adj = defaultdict(list)

    for edge in edges:
        s = edge.get("source")
        t = edge.get("target")
        if s not in node_ids or t not in node_ids:
            continue
        s_parent = _get_parent_id(node_by_id[s])
        t_parent = _get_parent_id(node_by_id[t])
        if s_parent == t_parent:
            adj[s].append(t)
            in_degree[t] += 1

    connected = {edge["source"] for edge in edges} | {edge["target"] for edge in edges}
    queue = deque(n for n in connected if in_degree[n] == 0)
    visited = 0
    while queue:
        node = queue.popleft()
        visited += 1
        for neighbor in adj[node]:
            in_degree[neighbor] -= 1
            if in_degree[neighbor] == 0:
                queue.append(neighbor)

    if visited != len(connected):
        violations.append(
            Violation(
                code="cycle",
                message="Workflow graph contains a cycle",
            )
        )
    return violations


def find_unreachable_nodes(nodes: list[dict], edges: list[dict]) -> list[str]:
    """Return IDs of non-start nodes that have no incoming edges."""
    connected_targets = {e["target"] for e in edges}
    unreachable: list[str] = []
    for node in nodes:
        if node.get("type") == "start":
            continue
        if node["id"] in connected_targets:
            continue
        unreachable.append(node["id"])
    return unreachable
