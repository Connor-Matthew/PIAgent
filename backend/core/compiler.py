from collections import defaultdict, deque
from langgraph.graph import StateGraph

from backend.core.state import WorkflowState
from backend.core.template import REF_RE
from backend.nodes.registry import node_registry
from backend.nodes.start_node import StartNode
from backend.nodes.end_node import EndNode
from backend.nodes.llm_node import LLMNode
from backend.nodes.tts_node import TTSNode
from backend.nodes.rag_node import RAGNode
from backend.nodes.agent_node import AgentNode
from backend.nodes.if_else_node import IfElseNode
from backend.nodes.iteration_node import IterationNode

# Register built-in nodes
for node_cls in (StartNode, EndNode, LLMNode, TTSNode, RAGNode, AgentNode, IfElseNode, IterationNode):
    try:
        node_registry.register(node_cls)
    except KeyError:
        pass


from dataclasses import dataclass, field
from typing import Any


@dataclass
class CompiledWorkflow:
    """Lightweight compilation result replacing LangGraph CompiledGraph."""

    nodes: dict[str, Any]                           # node_id -> instantiated node
    top_level_order: list[str]                      # execution order for top-level (no parentId) nodes
    children_by_parent: dict[str, list[str]]        # parent_id -> child node ids in subgraph topo order
    edges_by_source: dict[str, list[dict]]          # adjacency list for debugging / future use
    node_defs: dict[str, dict]                      # original node definitions


class CycleDetectedError(Exception):
    pass


class CompilerError(Exception):
    pass


class GraphCompiler:
    @staticmethod
    def _get_parent_id(node_def: dict) -> str | None:
        return (node_def.get("data") or {}).get("parentId")

    def _validate_parent_id_existence(self, nodes, node_ids):
        for node_def in nodes:
            pid = self._get_parent_id(node_def)
            if pid and pid not in node_ids:
                raise CompilerError(
                    f"Node '{node_def['id']}' has parentId '{pid}' which does not exist in the graph"
                )

    def _validate_start_end_no_parent(self, nodes):
        for node_def in nodes:
            if node_def["type"] in ("start", "end"):
                pid = self._get_parent_id(node_def)
                if pid:
                    raise CompilerError(
                        f"Node '{node_def['id']}' of type '{node_def['type']}' cannot have a parentId"
                    )

    def _validate_cross_scope_edges(self, nodes, edges):
        node_map = {n["id"]: n for n in nodes}
        for edge in edges:
            source_id = edge["source"]
            target_id = edge["target"]
            # Skip dangling edges; undeclared node check handles them later
            if source_id not in node_map or target_id not in node_map:
                continue
            s = node_map[source_id]
            t = node_map[target_id]
            s_parent = self._get_parent_id(s)
            t_parent = self._get_parent_id(t)

            if s_parent == t_parent:
                continue
            if t_parent == source_id:
                continue
            if s_parent == target_id:
                continue

            raise CompilerError(
                f"Invalid cross-scope edge: {source_id} -> {target_id}. "
                f"Edges must connect nodes within the same parent scope, "
                f"or connect a parent node directly to/from its child."
            )

    def _validate_subgraph_acyclicity(self, nodes, edges):
        parent_ids = set()
        for n in nodes:
            pid = self._get_parent_id(n)
            if pid:
                parent_ids.add(pid)

        for pid in parent_ids:
            child_ids = {n["id"] for n in nodes if self._get_parent_id(n) == pid}
            internal_edges = [
                e for e in edges
                if e["source"] in child_ids and e["target"] in child_ids
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
                raise CycleDetectedError(f"Subgraph under parent '{pid}' contains a cycle")

    def _validate_subgraph_connectivity(self, nodes, edges):
        parent_ids = set()
        for n in nodes:
            pid = self._get_parent_id(n)
            if pid:
                parent_ids.add(pid)

        for pid in parent_ids:
            child_ids = {n["id"] for n in nodes if self._get_parent_id(n) == pid}
            internal_edges = [
                e for e in edges
                if e["source"] in child_ids and e["target"] in child_ids
            ]

            has_incoming = set()
            for e in internal_edges:
                has_incoming.add(e["target"])

            entry_nodes = child_ids - has_incoming
            if not entry_nodes:
                raise CompilerError(
                    f"Subgraph under parent '{pid}' has no entry node. "
                    f"At least one child node must have no incoming edges from sibling nodes."
                )

    def validate(self, graph_json: dict, db=None):
        """Validate DAG: detect cycles using Kahn's algorithm."""
        nodes = {n["id"]: n for n in graph_json["nodes"]}
        node_ids = set(nodes.keys())

        # Check for duplicate node IDs
        ids = [n["id"] for n in graph_json["nodes"]]
        if len(ids) != len(node_ids):
            raise ValueError("Duplicate node IDs found in workflow graph")

        # Check node types are registered
        for node_def in graph_json["nodes"]:
            try:
                node_registry.get(node_def["type"])
            except KeyError:
                raise ValueError(f"Unknown node type: {node_def['type']}")

        # Structural: start/end nodes cannot have a parentId
        self._validate_start_end_no_parent(graph_json["nodes"])

        # Structural: parentId must point to a real node in the graph
        self._validate_parent_id_existence(graph_json["nodes"], node_ids)

        # Validate exactly one start and one end node
        start_nodes = [n for n in graph_json["nodes"] if n["type"] == "start"]
        end_nodes = [n for n in graph_json["nodes"] if n["type"] == "end"]

        if len(start_nodes) == 0:
            raise CompilerError("Workflow must contain exactly one start node, found 0")
        if len(start_nodes) > 1:
            raise CompilerError(f"Workflow must contain exactly one start node, found {len(start_nodes)}")
        if len(end_nodes) == 0:
            raise CompilerError("Workflow must contain exactly one end node, found 0")
        if len(end_nodes) > 1:
            raise CompilerError(f"Workflow must contain exactly one end node, found {len(end_nodes)}")

        # Validate end node reference outputs
        for end_node in end_nodes:
            for out in (end_node.get("data") or {}).get("outputs", []):
                if out.get("source") == "reference":
                    value = out.get("value", "")
                    if not REF_RE.fullmatch(value):
                        raise CompilerError(
                            f"End node '{end_node['id']}' reference output '{out['name']}' "
                            f"must match {{nodeId.fieldName}} format, got: {value}"
                        )
                    ref_match = REF_RE.match(value)
                    if ref_match:
                        ref_node_id = ref_match.group(1)
                        ref_field = ref_match.group(2)
                        if not ref_field:
                            raise CompilerError(
                                f"End node '{end_node['id']}' reference output '{out['name']}' "
                                f"must specify a field name, got: {value}"
                            )
                        if ref_node_id not in node_ids:
                            raise CompilerError(
                                f"End node '{end_node['id']}' reference output '{out['name']}' "
                                f"points to unknown node: {ref_node_id}"
                            )

        # Validate LLM node provider_ids
        if db is not None:
            from backend.models.provider import Provider
            for node_def in graph_json["nodes"]:
                if node_def["type"] == "llm":
                    provider_id = (node_def.get("data") or {}).get("provider_id")
                    if not provider_id:
                        raise CompilerError(f"LLM node '{node_def['id']}' must have a provider_id")
                    row = db.query(Provider).filter(Provider.id == provider_id).first()
                    if not row:
                        raise CompilerError(f"LLM node '{node_def['id']}' references unknown provider: {provider_id}")
                    if not row.enabled:
                        raise CompilerError(f"LLM node '{node_def['id']}' references disabled provider: {provider_id}")

        # Structural: cross-scope edge restrictions
        self._validate_cross_scope_edges(graph_json["nodes"], graph_json["edges"])

        # Structural: each subgraph must be acyclic
        self._validate_subgraph_acyclicity(graph_json["nodes"], graph_json["edges"])

        # Structural: each subgraph must have at least one entry node
        self._validate_subgraph_connectivity(graph_json["nodes"], graph_json["edges"])

        # Global DAG cycle detection: only consider edges within the same parent scope.
        # Cross-scope edges (parent <-> child) are allowed and must not participate
        # in global cycle detection because they belong to different execution scopes.
        in_degree = defaultdict(int)
        adj = defaultdict(list)
        scope_groups = defaultdict(set)

        for n in graph_json["nodes"]:
            pid = self._get_parent_id(n)
            scope_groups[pid].add(n["id"])

        for edge in graph_json["edges"]:
            if edge["source"] not in node_ids:
                raise ValueError(f"Edge references undeclared source node: {edge['source']}")
            if edge["target"] not in node_ids:
                raise ValueError(f"Edge references undeclared target node: {edge['target']}")
            s = nodes[edge["source"]]
            t = nodes[edge["target"]]
            s_parent = self._get_parent_id(s)
            t_parent = self._get_parent_id(t)
            # Only include edge in global cycle check if both ends share the same scope
            if s_parent == t_parent:
                adj[edge["source"]].append(edge["target"])
                in_degree[edge["target"]] += 1

        # Only check nodes that belong to edges; unconnected orphan nodes are ignored
        connected = {edge["source"] for edge in graph_json["edges"]} | {
            edge["target"] for edge in graph_json["edges"]
        }
        queue = deque(n for n in connected if in_degree[n] == 0)
        visited = 0

        while queue:
            node = queue.popleft()
            visited += 1
            for neighbor in adj[node]:
                in_degree[neighbor] -= 1
                if in_degree[neighbor] == 0:
                    queue.append(neighbor)

        # We compare against the number of *connected* nodes, not all nodes,
        # because unconnected nodes on the canvas are allowed.
        if visited != len(connected):
            raise CycleDetectedError("Workflow graph contains a cycle")

    def topological_sort(self, graph_json: dict, db=None) -> list[str]:
        """Return nodes in topological order using Kahn's algorithm.

        Only nodes that are connected by edges are included in the result.
        Unconnected nodes on the canvas are ignored.
        """
        self.validate(graph_json, db=db)

        in_degree = defaultdict(int)
        adj = defaultdict(list)

        for edge in graph_json["edges"]:
            adj[edge["source"]].append(edge["target"])
            in_degree[edge["target"]] += 1

        connected = {edge["source"] for edge in graph_json["edges"]} | {
            edge["target"] for edge in graph_json["edges"]
        }
        queue = deque(n for n in connected if in_degree[n] == 0)
        order = []

        while queue:
            node = queue.popleft()
            order.append(node)
            for neighbor in adj[node]:
                in_degree[neighbor] -= 1
                if in_degree[neighbor] == 0:
                    queue.append(neighbor)

        return order

    def _scope_topological_sort(self, scope_node_ids: set[str], edges: list[dict]) -> list[str]:
        """Return a topological order for a subset of nodes (a scope).

        All nodes in scope_node_ids are included, even if they have no edges.
        """
        in_degree = defaultdict(int)
        adj = defaultdict(list)

        for edge in edges:
            if edge["source"] in scope_node_ids and edge["target"] in scope_node_ids:
                adj[edge["source"]].append(edge["target"])
                in_degree[edge["target"]] += 1

        queue = deque(n for n in scope_node_ids if in_degree[n] == 0)
        order = []
        visited = set()

        while queue:
            node = queue.popleft()
            if node in visited:
                continue
            visited.add(node)
            order.append(node)
            for neighbor in adj[node]:
                in_degree[neighbor] -= 1
                if in_degree[neighbor] == 0:
                    queue.append(neighbor)

        # Append any remaining unvisited nodes (isolated within this scope)
        for node in scope_node_ids:
            if node not in visited:
                order.append(node)

        return order

    def topological_sort(self, graph_json: dict, db=None) -> list[str]:
        """Return nodes in topological order using Kahn's algorithm.

        Only nodes that are connected by edges are included in the result.
        Unconnected nodes on the canvas are ignored.
        """
        self.validate(graph_json, db=db)

        in_degree = defaultdict(int)
        adj = defaultdict(list)

        for edge in graph_json["edges"]:
            adj[edge["source"]].append(edge["target"])
            in_degree[edge["target"]] += 1

        connected = {edge["source"] for edge in graph_json["edges"]} | {
            edge["target"] for edge in graph_json["edges"]
        }
        queue = deque(n for n in connected if in_degree[n] == 0)
        order = []

        while queue:
            node = queue.popleft()
            order.append(node)
            for neighbor in adj[node]:
                in_degree[neighbor] -= 1
                if in_degree[neighbor] == 0:
                    queue.append(neighbor)

        return order

    def compile(self, graph_json: dict, db=None) -> CompiledWorkflow:
        """Compile workflow JSON into a CompiledWorkflow object.

        Replaces the previous LangGraph-based compilation with a lightweight
        structure that the ExecutionEngine uses for its own scheduling.
        """
        self.validate(graph_json, db=db)

        node_map = {n["id"]: n for n in graph_json["nodes"]}
        node_ids = set(node_map.keys())

        # Build adjacency list for debugging / future extensions
        edges_by_source: dict[str, list[dict]] = defaultdict(list)
        for edge in graph_json["edges"]:
            edges_by_source[edge["source"]].append(edge)

        # Instantiate all registered nodes
        instantiated: dict[str, Any] = {}
        for node_def in graph_json["nodes"]:
            node_cls = node_registry.get(node_def["type"])
            config = {**(node_def.get("data") or {}), "id": node_def["id"]}
            instantiated[node_def["id"]] = node_cls(config=config)

        # Top-level scope: nodes without a parentId that are connected by edges
        top_level_ids = {n["id"] for n in graph_json["nodes"] if not self._get_parent_id(n)}
        top_level_edges = [
            e for e in graph_json["edges"]
            if e["source"] in top_level_ids and e["target"] in top_level_ids
        ]
        connected_top = {e["source"] for e in top_level_edges} | {e["target"] for e in top_level_edges}
        top_level_ids = top_level_ids & connected_top
        top_level_order = self._scope_topological_sort(top_level_ids, top_level_edges)

        # Subgraph scopes: group children by their parentId and topo-sort each
        children_by_parent: dict[str, list[str]] = {}
        parent_ids = {
            self._get_parent_id(n) for n in graph_json["nodes"] if self._get_parent_id(n)
        }
        for pid in parent_ids:
            child_ids = {n["id"] for n in graph_json["nodes"] if self._get_parent_id(n) == pid}
            scope_edges = [
                e for e in graph_json["edges"]
                if e["source"] in child_ids and e["target"] in child_ids
            ]
            children_by_parent[pid] = self._scope_topological_sort(child_ids, scope_edges)

        return CompiledWorkflow(
            nodes=instantiated,
            top_level_order=top_level_order,
            children_by_parent=children_by_parent,
            edges_by_source=dict(edges_by_source),
            node_defs=node_map,
        )
