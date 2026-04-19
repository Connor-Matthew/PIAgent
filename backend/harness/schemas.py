"""PIAgent Harness v2 — Core schemas for Decision, GraphAction, and validation."""

from typing import Annotated, Any, Literal

from pydantic import BaseModel, Field, TypeAdapter


# ───────────────────────────────────────────────
# GraphAction primitives (what ProposeAction carries)
# ───────────────────────────────────────────────

class AddNodeAction(BaseModel):
    kind: Literal["add_node"] = "add_node"
    node_type: str
    node_id: str | None = Field(default=None, description="Auto-generated if omitted")
    config: dict = Field(default_factory=dict)


class AddEdgeAction(BaseModel):
    kind: Literal["add_edge"] = "add_edge"
    source: str
    target: str


class UpdateNodeConfigAction(BaseModel):
    kind: Literal["update_node_config"] = "update_node_config"
    node_id: str
    config: dict


class DeleteNodeAction(BaseModel):
    kind: Literal["delete_node"] = "delete_node"
    node_id: str


class DeleteEdgeAction(BaseModel):
    kind: Literal["delete_edge"] = "delete_edge"
    source: str
    target: str


GraphAction = Annotated[
    AddNodeAction | AddEdgeAction | UpdateNodeConfigAction | DeleteNodeAction | DeleteEdgeAction,
    Field(discriminator="kind"),
]


# ───────────────────────────────────────────────
# Decision discriminated union (what LeadAgent emits)
# ───────────────────────────────────────────────

class CallTool(BaseModel):
    kind: Literal["call_tool"] = "call_tool"
    tool: str
    args: dict = Field(default_factory=dict)


class LoadSkill(BaseModel):
    kind: Literal["load_skill"] = "load_skill"
    skill: str


class ProposeAction(BaseModel):
    kind: Literal["propose_action"] = "propose_action"
    action: GraphAction


class AskUser(BaseModel):
    kind: Literal["ask_user"] = "ask_user"
    question: str
    options: list[str] | None = Field(default=None, description="If provided, render as choice buttons")


class Finalize(BaseModel):
    kind: Literal["finalize"] = "finalize"
    reason: str


Decision = Annotated[
    CallTool | LoadSkill | ProposeAction | AskUser | Finalize,
    Field(discriminator="kind"),
]

_DECISION_ADAPTER = TypeAdapter(Decision)


def _normalize_graph_action_payload(payload: Any) -> Any:
    if not isinstance(payload, dict):
        return payload

    normalized = dict(payload)
    if "kind" not in normalized and isinstance(normalized.get("type"), str):
        normalized["kind"] = normalized["type"]

    kind = normalized.get("kind")

    if kind == "add_node":
        node = normalized.get("node")
        if isinstance(node, dict):
            normalized.setdefault("node_type", node.get("type") or node.get("node_type"))
            normalized.setdefault("node_id", node.get("id") or node.get("node_id"))
            node_config = node.get("data")
            if node_config is None:
                node_config = node.get("config")
            if node_config is not None:
                normalized.setdefault("config", node_config)
        if "node_type" not in normalized:
            nt = normalized.get("type") if normalized.get("type") != kind else None
            if nt is None:
                nt = normalized.get("nodeType") or normalized.get("kind_of_node")
            if nt is not None:
                normalized["node_type"] = nt
        if "node_id" not in normalized:
            nid = normalized.get("id") or normalized.get("nodeId")
            if nid is not None:
                normalized["node_id"] = nid
        normalized.setdefault("config", {})

    elif kind == "add_edge":
        edge = normalized.get("edge")
        if isinstance(edge, dict):
            normalized.setdefault(
                "source",
                edge.get("source") or edge.get("from_node") or edge.get("from"),
            )
            normalized.setdefault(
                "target",
                edge.get("target") or edge.get("to_node") or edge.get("to"),
            )
        if "source" not in normalized:
            src = normalized.get("from_node") or normalized.get("from") or normalized.get("source_id")
            if src is not None:
                normalized["source"] = src
        if "target" not in normalized:
            tgt = normalized.get("to_node") or normalized.get("to") or normalized.get("target_id")
            if tgt is not None:
                normalized["target"] = tgt

    elif kind == "update_node_config":
        node = normalized.get("node")
        if isinstance(node, dict):
            normalized.setdefault("node_id", node.get("id") or node.get("node_id"))
        config = normalized.get("patch")
        if config is None:
            config = normalized.get("config")
        if config is None and isinstance(node, dict):
            config = node.get("data") or node.get("config")
        normalized["config"] = config or {}

    elif kind == "delete_node":
        node = normalized.get("node")
        if isinstance(node, dict):
            normalized.setdefault("node_id", node.get("id") or node.get("node_id"))

    elif kind == "delete_edge":
        edge = normalized.get("edge")
        if isinstance(edge, dict):
            normalized.setdefault(
                "source",
                edge.get("source") or edge.get("from_node") or edge.get("from"),
            )
            normalized.setdefault(
                "target",
                edge.get("target") or edge.get("to_node") or edge.get("to"),
            )
        if "source" not in normalized:
            src = normalized.get("from_node") or normalized.get("from") or normalized.get("source_id")
            if src is not None:
                normalized["source"] = src
        if "target" not in normalized:
            tgt = normalized.get("to_node") or normalized.get("to") or normalized.get("target_id")
            if tgt is not None:
                normalized["target"] = tgt

    return normalized


def normalize_decision_payload(payload: Any) -> Any:
    if not isinstance(payload, dict):
        return payload

    normalized = dict(payload)

    if "kind" not in normalized:
        legacy_kind = normalized.get("decision")
        if isinstance(legacy_kind, str):
            normalized["kind"] = legacy_kind
        elif normalized.get("done") is True:
            normalized["kind"] = "finalize"
        elif "action" in normalized:
            normalized["kind"] = "propose_action"

    if normalized.get("kind") == "call_skill":
        normalized["kind"] = "load_skill"

    if normalized.get("kind") in {"validate_graph", "validate", "commit", "commit_graph", "submit", "done"}:
        reason = (
            normalized.get("reason")
            or normalized.get("reasoning")
            or normalized.get("summary")
            or "graph is ready to validate and submit"
        )
        return {"kind": "finalize", "reason": reason}

    kind = normalized.get("kind")

    if kind == "call_tool":
        if "tool" not in normalized:
            tool_name = normalized.get("tool_name") or normalized.get("name")
            if tool_name is not None:
                normalized["tool"] = tool_name
        if "args" not in normalized:
            args = normalized.get("arguments")
            if args is None:
                args = normalized.get("tool_input")
            if args is None:
                args = normalized.get("skill_input")
            normalized["args"] = args or {}

    elif kind == "load_skill":
        if "skill" not in normalized:
            skill_name = normalized.get("skill_name") or normalized.get("name")
            if skill_name is not None:
                normalized["skill"] = skill_name

    elif kind == "propose_action":
        action = _normalize_graph_action_payload(normalized.get("action"))
        if isinstance(action, dict) and action.get("kind") == "commit_graph":
            return {
                "kind": "finalize",
                "reason": normalized.get("reason")
                or normalized.get("reasoning")
                or "graph is ready to submit",
            }
        normalized["action"] = action

    elif kind == "finalize":
        if "reason" not in normalized:
            reason = normalized.get("reasoning") or normalized.get("summary")
            if reason is None and normalized.get("done") is True:
                reason = "graph is ready to submit"
            if reason is not None:
                normalized["reason"] = reason

    return normalized


def validate_decision_payload(payload: Any) -> Decision:
    return _DECISION_ADAPTER.validate_python(normalize_decision_payload(payload))


# ───────────────────────────────────────────────
# Validation findings
# ───────────────────────────────────────────────

class Finding(BaseModel):
    severity: Literal["error", "warning"]
    code: str
    message: str
    node_id: str | None = Field(default=None)
