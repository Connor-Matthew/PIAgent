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

# Register built-in nodes
for node_cls in (StartNode, EndNode, LLMNode, TTSNode, RAGNode, AgentNode):
    try:
        node_registry.register(node_cls)
    except KeyError:
        pass


class CycleDetectedError(Exception):
    pass


class CompilerError(Exception):
    pass


class GraphCompiler:
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

        in_degree = defaultdict(int)
        adj = defaultdict(list)

        for edge in graph_json["edges"]:
            if edge["source"] not in node_ids:
                raise ValueError(f"Edge references undeclared source node: {edge['source']}")
            if edge["target"] not in node_ids:
                raise ValueError(f"Edge references undeclared target node: {edge['target']}")
            adj[edge["source"]].append(edge["target"])
            in_degree[edge["target"]] += 1

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

    def _make_handler(self, node_instance):
        async def handler(state: WorkflowState):
            return await node_instance.execute(state)
        return handler

    def compile(self, graph_json: dict, db=None):
        """Compile workflow JSON into a LangGraph CompiledGraph."""
        graph = StateGraph(WorkflowState)

        # Set entry point to the first node in topological order
        order = self.topological_sort(graph_json, db=db)
        if not order:
            raise ValueError("Workflow graph has no nodes")

        connected = set(order)

        # Add nodes (only connected ones)
        for node_def in graph_json["nodes"]:
            if node_def["id"] not in connected:
                continue
            node_cls = node_registry.get(node_def["type"])
            config = {**(node_def.get("data") or {}), "id": node_def["id"]}
            node_instance = node_cls(config=config)
            handler = self._make_handler(node_instance)
            graph.add_node(node_def["id"], handler)

        graph.set_entry_point(order[0])

        # Add edges
        for edge in graph_json["edges"]:
            graph.add_edge(edge["source"], edge["target"])

        # Set finish point to the last node in topological order
        graph.set_finish_point(order[-1])

        return graph.compile()
