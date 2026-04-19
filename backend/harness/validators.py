"""PIAgent Harness v2 — Graph validation (pure functions, no LLM).

Rules from spec §8.2:
- missing_start: error
- missing_end: error
- cycle: error
- dangling_edge: error
- unbound_provider: error
- bad_template_ref: error
- unreachable_node: warning
- too_simple: warning
"""

from __future__ import annotations

from collections import defaultdict, deque
from typing import TYPE_CHECKING

from backend.core.template import REF_RE
from backend.harness.schemas import Finding

if TYPE_CHECKING:
    from sqlalchemy.orm import Session


def validate_graph(graph: dict, db: "Session | None" = None) -> list[Finding]:
    """Validate a workflow graph and return a list of findings.

    This function performs NO LLM calls — it is entirely deterministic.
    """
    findings: list[Finding] = []
    nodes = graph.get("nodes", [])
    edges = graph.get("edges", [])

    node_ids = {n["id"] for n in nodes}
    node_by_id = {n["id"]: n for n in nodes}
    node_types = {n["id"]: n.get("type", "") for n in nodes}

    # ── structural checks ──

    start_nodes = [n for n in nodes if n.get("type") == "start"]
    end_nodes = [n for n in nodes if n.get("type") == "end"]

    if not start_nodes:
        findings.append(Finding(
            severity="error",
            code="missing_start",
            message="Graph must contain exactly one start node, found 0",
        ))
    if len(start_nodes) > 1:
        findings.append(Finding(
            severity="error",
            code="multiple_start",
            message=f"Graph must contain exactly one start node, found {len(start_nodes)}",
        ))

    if not end_nodes:
        findings.append(Finding(
            severity="error",
            code="missing_end",
            message="Graph must contain exactly one end node, found 0",
        ))
    if len(end_nodes) > 1:
        findings.append(Finding(
            severity="error",
            code="multiple_end",
            message=f"Graph must contain exactly one end node, found {len(end_nodes)}",
        ))

    # ── dangling edges ──

    for edge in edges:
        src = edge.get("source", "")
        tgt = edge.get("target", "")
        if src not in node_ids:
            findings.append(Finding(
                severity="error",
                code="dangling_edge",
                message=f"Edge references undeclared source node: {src}",
            ))
        if tgt not in node_ids:
            findings.append(Finding(
                severity="error",
                code="dangling_edge",
                message=f"Edge references undeclared target node: {tgt}",
            ))

    # ── cycle detection (Kahn) ──

    if node_ids:
        in_degree = defaultdict(int)
        adj = defaultdict(list)
        for edge in edges:
            s = edge.get("source")
            t = edge.get("target")
            if s in node_ids and t in node_ids:
                adj[s].append(t)
                in_degree[t] += 1

        queue = deque(n for n in node_ids if in_degree[n] == 0)
        visited = 0
        while queue:
            node = queue.popleft()
            visited += 1
            for neighbor in adj[node]:
                in_degree[neighbor] -= 1
                if in_degree[neighbor] == 0:
                    queue.append(neighbor)

        if visited != len(node_ids):
            findings.append(Finding(
                severity="error",
                code="cycle",
                message="Workflow graph contains a cycle",
            ))

    # ── template references in end node ──

    for end_node in end_nodes:
        data = end_node.get("data")
        if not isinstance(data, dict):
            data = {}
        outputs = data.get("outputs", [])
        if not isinstance(outputs, list):
            outputs = []
        for out in outputs:
            if not isinstance(out, dict):
                continue
            if out.get("source") == "reference":
                value = out.get("value", "")
                if not REF_RE.fullmatch(value):
                    findings.append(Finding(
                        severity="error",
                        code="bad_template_ref",
                        message=(
                            f"End node '{end_node['id']}' reference output "
                            f"'{out['name']}' must match {{nodeId.fieldName}} format, got: {value}"
                        ),
                        node_id=end_node["id"],
                    ))
                else:
                    match = REF_RE.match(value)
                    if match:
                        ref_node_id = match.group(1)
                        if ref_node_id not in node_ids:
                            findings.append(Finding(
                                severity="error",
                                code="bad_template_ref",
                                message=(
                                    f"End node '{end_node['id']}' reference output "
                                    f"points to unknown node: {ref_node_id}"
                                ),
                                node_id=end_node["id"],
                            ))

    # ── provider checks (require db) ──

    if db is not None:
        from backend.models.provider import Provider

        for node in nodes:
            node_data = node.get("data") if isinstance(node.get("data"), dict) else {}
            if node.get("type") == "llm":
                provider_id = node_data.get("provider_id")
                if not provider_id:
                    findings.append(Finding(
                        severity="error",
                        code="unbound_provider",
                        message=f"LLM node '{node['id']}' must have a provider_id",
                        node_id=node["id"],
                    ))
                else:
                    row = db.query(Provider).filter(Provider.id == provider_id).first()
                    if not row:
                        findings.append(Finding(
                            severity="error",
                            code="unbound_provider",
                            message=f"LLM node '{node['id']}' references unknown provider: {provider_id}",
                            node_id=node["id"],
                        ))
                    elif not row.enabled:
                        findings.append(Finding(
                            severity="error",
                            code="unbound_provider",
                            message=f"LLM node '{node['id']}' references disabled provider: {provider_id}",
                            node_id=node["id"],
                        ))

            if node.get("type") == "tts":
                provider_id = node_data.get("provider_id")
                if not provider_id:
                    findings.append(Finding(
                        severity="error",
                        code="unbound_provider",
                        message=f"TTS node '{node['id']}' must have a provider_id",
                        node_id=node["id"],
                    ))
                else:
                    row = db.query(Provider).filter(Provider.id == provider_id).first()
                    if not row:
                        findings.append(Finding(
                            severity="error",
                            code="unbound_provider",
                            message=f"TTS node '{node['id']}' references unknown provider: {provider_id}",
                            node_id=node["id"],
                        ))
                    elif not row.enabled:
                        findings.append(Finding(
                            severity="error",
                            code="unbound_provider",
                            message=f"TTS node '{node['id']}' references disabled provider: {provider_id}",
                            node_id=node["id"],
                        ))

    # ── warnings ──

    # Unreachable nodes (non-start nodes with no incoming edges)
    connected_targets = {e["target"] for e in edges}
    for node in nodes:
        if node.get("type") == "start":
            continue
        if node["id"] in connected_targets:
            continue
        is_end = node.get("type") == "end"
        findings.append(Finding(
            severity="error" if is_end else "warning",
            code="unreachable_end" if is_end else "unreachable_node",
            message=(
                f"End node '{node['id']}' has no incoming edges; the workflow produces no output"
                if is_end
                else f"Node '{node['id']}' has no incoming edges and may be unreachable"
            ),
            node_id=node["id"],
        ))

    # Start nodes with no outgoing edges
    connected_sources = {e["source"] for e in edges}
    for start in start_nodes:
        if start["id"] not in connected_sources:
            findings.append(Finding(
                severity="error",
                code="dangling_start",
                message=f"Start node '{start['id']}' has no outgoing edges",
                node_id=start["id"],
            ))

    # Too simple (only start -> end direct)
    if len(nodes) == 2 and len(start_nodes) == 1 and len(end_nodes) == 1 and len(edges) == 1:
        findings.append(Finding(
            severity="warning",
            code="too_simple",
            message="Graph only contains Start -> End; the user's intent may not be fully implemented",
        ))

    return findings
