"""WorkflowGraph v2 schema — single source of truth for graph shape.

This module provides Pydantic models for the workflow graph contract.
It supports reading legacy v1 graphs (no ``version`` field) and normalising
them to the v2 structure.
"""

from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field


class Position(BaseModel):
    model_config = ConfigDict(extra="forbid")

    x: float
    y: float


class WorkflowNode(BaseModel):
    """A node in a WorkflowGraph.

    Structural fields (``parentId``, ``branchId``) live at the top level so
    that the compiler and engine do not need to dig into arbitrary ``data``
    dicts.
    """

    model_config = ConfigDict(extra="allow")

    id: str = Field(min_length=1)
    type: str = Field(min_length=1)
    position: Position | None = None

    # Structural fields — used by compiler / engine
    parentId: str | None = Field(default=None, alias="parentId")
    branchId: str | None = Field(default=None, alias="branchId")

    # Display meta
    label: str | None = None
    locked: bool | None = None

    # Business configuration (provider_id, prompt, etc.)
    config: dict[str, Any] = Field(default_factory=dict)


class WorkflowEdge(BaseModel):
    """An edge in a WorkflowGraph.

    ``sourceHandle`` is **UI metadata only** and must not influence execution
    routing.  The backend compiler derives routing from ``parentId`` and
    ``branchId``.
    """

    model_config = ConfigDict(extra="forbid")

    id: str | None = None
    source: str = Field(min_length=1)
    target: str = Field(min_length=1)
    sourceHandle: str | None = Field(default=None, alias="sourceHandle")


class WorkflowGraph(BaseModel):
    """WorkflowGraph v2 — the canonical graph contract.

    All new saves must write ``version: 2``.  The loader accepts v1 graphs
    (missing ``version``) and normalises them automatically.
    """

    model_config = ConfigDict(extra="forbid")

    version: Literal[2] = 2
    nodes: list[WorkflowNode] = Field(default_factory=list)
    edges: list[WorkflowEdge] = Field(default_factory=list)


# ---------------------------------------------------------------------------
# v1 → v2 normalisation helpers
# ---------------------------------------------------------------------------

def _upgrade_v1_node(node_def: dict[str, Any]) -> dict[str, Any]:
    """Convert a v1 node dict to the v2 shape.

    v1 nodes store ``parentId`` and ``branchId`` inside ``data``.  v2 hoists
    them to the top level and moves everything else into ``config``.
    """
    result: dict[str, Any] = {
        "id": node_def["id"],
        "type": node_def.get("type", ""),
    }

    if "position" in node_def:
        result["position"] = node_def["position"]

    data = node_def.get("data") or {}

    # Hoist structural fields
    if isinstance(data.get("parentId"), str):
        result["parentId"] = data["parentId"]
    if isinstance(data.get("branchId"), str):
        result["branchId"] = data["branchId"]

    # Hoist display meta
    if isinstance(data.get("label"), str):
        result["label"] = data["label"]
    if isinstance(data.get("locked"), bool):
        result["locked"] = data["locked"]

    # Everything else becomes config
    config: dict[str, Any] = {}
    for key, value in data.items():
        if key in ("parentId", "branchId", "label", "locked", "nodeType", "config"):
            continue
        config[key] = value

    # If the caller already had a flat v1 shape with top-level fields mixed
    # into ``data`` (e.g. provider_id, prompt), those are now in config.
    nested_config = data.get("config")
    if isinstance(nested_config, dict):
        config.update(nested_config)

    result["config"] = config
    return result


def _upgrade_v1_edge(edge_def: dict[str, Any]) -> dict[str, Any]:
    """Convert a v1 edge dict to the v2 shape."""
    result: dict[str, Any] = {
        "source": edge_def["source"],
        "target": edge_def["target"],
    }
    if "id" in edge_def:
        result["id"] = edge_def["id"]
    if "sourceHandle" in edge_def:
        result["sourceHandle"] = edge_def["sourceHandle"]
    return result


def load_graph(raw: dict[str, Any]) -> WorkflowGraph:
    """Load a workflow graph, upgrading from v1 if necessary.

    Raises ``ValueError`` on malformed input.
    """
    version = raw.get("version")

    if version == 2:
        return WorkflowGraph.model_validate(raw)

    # Treat everything else as v1 (legacy)
    nodes = [_upgrade_v1_node(n) for n in raw.get("nodes", [])]
    edges = [_upgrade_v1_edge(e) for e in raw.get("edges", [])]
    return WorkflowGraph(version=2, nodes=nodes, edges=edges)


def dump_graph(graph: WorkflowGraph) -> dict[str, Any]:
    """Serialize a WorkflowGraph to the canonical v2 JSON dict.

    The returned dict is safe to send to the frontend or store in the DB.
    """
    return graph.model_dump(by_alias=True, exclude_none=False)


def get_node_config(node: WorkflowNode | dict[str, Any]) -> dict[str, Any]:
    if isinstance(node, WorkflowNode):
        return dict(node.config or {})
    if isinstance(node.get("config"), dict):
        return dict(node["config"])
    data = node.get("data") if isinstance(node.get("data"), dict) else {}
    if isinstance(data.get("config"), dict):
        return dict(data["config"])
    return {
        key: value
        for key, value in data.items()
        if key not in ("parentId", "branchId", "label", "locked", "nodeType")
    }


def get_node_parent_id(node: WorkflowNode | dict[str, Any]) -> str | None:
    if isinstance(node, WorkflowNode):
        return node.parentId
    if isinstance(node.get("parentId"), str):
        return node["parentId"]
    data = node.get("data") if isinstance(node.get("data"), dict) else {}
    return data.get("parentId") if isinstance(data.get("parentId"), str) else None


def get_node_branch_id(node: WorkflowNode | dict[str, Any]) -> str | None:
    if isinstance(node, WorkflowNode):
        return node.branchId
    if isinstance(node.get("branchId"), str):
        return node["branchId"]
    data = node.get("data") if isinstance(node.get("data"), dict) else {}
    return data.get("branchId") if isinstance(data.get("branchId"), str) else None
