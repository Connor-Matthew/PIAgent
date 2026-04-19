from collections import defaultdict, deque
from langgraph.graph import StateGraph

from backend.core import graph_rules
from backend.core.graph_schema import dump_graph, get_node_config, get_node_parent_id, load_graph
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
        return get_node_parent_id(node_def)

    def _normalize(self, graph_json: dict) -> dict:
        return dump_graph(load_graph(graph_json))

    def _validate_parent_id_existence(self, nodes):
        for v in graph_rules.check_parent_id_existence(nodes):
            raise CompilerError(v.message)

    def _validate_start_end_no_parent(self, nodes):
        for v in graph_rules.check_start_end_no_parent(nodes):
            raise CompilerError(v.message)

    def _validate_cross_scope_edges(self, nodes, edges):
        for v in graph_rules.check_cross_scope_edges(nodes, edges):
            raise CompilerError(v.message)

    def _validate_subgraph_acyclicity(self, nodes, edges):
        for v in graph_rules.check_subgraph_acyclicity(nodes, edges):
            raise CycleDetectedError(v.message)

    def _validate_subgraph_connectivity(self, nodes, edges):
        for v in graph_rules.check_subgraph_connectivity(nodes, edges):
            raise CompilerError(v.message)

    def validate(self, graph_json: dict, db=None):
        """Validate DAG: detect cycles using Kahn's algorithm."""
        graph_json = self._normalize(graph_json)
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
        self._validate_parent_id_existence(graph_json["nodes"])

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
            for out in get_node_config(end_node).get("outputs", []):
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
                    provider_id = get_node_config(node_def).get("provider_id")
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

        # Dangling edge check (preserved from original inline cycle detection)
        for edge in graph_json["edges"]:
            if edge["source"] not in node_ids:
                raise ValueError(f"Edge references undeclared source node: {edge['source']}")
            if edge["target"] not in node_ids:
                raise ValueError(f"Edge references undeclared target node: {edge['target']}")

        # Global DAG cycle detection
        for v in graph_rules.check_global_acyclicity(graph_json["nodes"], graph_json["edges"]):
            raise CycleDetectedError(v.message)

    def topological_sort(self, graph_json: dict, db=None) -> list[str]:
        """Return nodes in topological order using Kahn's algorithm.

        Only nodes that are connected by edges are included in the result.
        Unconnected nodes on the canvas are ignored.
        """
        graph_json = self._normalize(graph_json)
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

    def compile(self, graph_json: dict, db=None) -> CompiledWorkflow:
        """Compile workflow JSON into a CompiledWorkflow object.

        Replaces the previous LangGraph-based compilation with a lightweight
        structure that the ExecutionEngine uses for its own scheduling.
        """
        graph_json = self._normalize(graph_json)
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
            config = {**get_node_config(node_def), "id": node_def["id"]}
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
