from collections import defaultdict, deque
from langgraph.graph import StateGraph

from backend.core.state import WorkflowState
from backend.nodes.registry import node_registry
from backend.nodes.start_node import StartNode
from backend.nodes.end_node import EndNode
from backend.nodes.llm_node import LLMNode

# Register built-in nodes
for node_cls in (StartNode, EndNode, LLMNode):
    try:
        node_registry.register(node_cls)
    except KeyError:
        pass


class CycleDetectedError(Exception):
    pass


class GraphCompiler:
    def validate(self, graph_json: dict):
        """Validate DAG: detect cycles using Kahn's algorithm."""
        nodes = {n["id"] for n in graph_json["nodes"]}

        # Check for duplicate node IDs
        node_ids = [n["id"] for n in graph_json["nodes"]]
        if len(node_ids) != len(nodes):
            raise ValueError("Duplicate node IDs found in workflow graph")

        # Check node types are registered
        for node_def in graph_json["nodes"]:
            try:
                node_registry.get(node_def["type"])
            except KeyError:
                raise ValueError(f"Unknown node type: {node_def['type']}")

        in_degree = defaultdict(int)
        adj = defaultdict(list)

        for edge in graph_json["edges"]:
            if edge["source"] not in nodes:
                raise ValueError(f"Edge references undeclared source node: {edge['source']}")
            if edge["target"] not in nodes:
                raise ValueError(f"Edge references undeclared target node: {edge['target']}")
            adj[edge["source"]].append(edge["target"])
            in_degree[edge["target"]] += 1

        queue = deque(n for n in nodes if in_degree[n] == 0)
        visited = 0

        while queue:
            node = queue.popleft()
            visited += 1
            for neighbor in adj[node]:
                in_degree[neighbor] -= 1
                if in_degree[neighbor] == 0:
                    queue.append(neighbor)

        if visited != len(nodes):
            raise CycleDetectedError("Workflow graph contains a cycle")

    def topological_sort(self, graph_json: dict) -> list[str]:
        """Return nodes in topological order using Kahn's algorithm."""
        self.validate(graph_json)

        nodes = {n["id"] for n in graph_json["nodes"]}
        in_degree = defaultdict(int)
        adj = defaultdict(list)

        for edge in graph_json["edges"]:
            adj[edge["source"]].append(edge["target"])
            in_degree[edge["target"]] += 1

        queue = deque(n for n in nodes if in_degree[n] == 0)
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

    def compile(self, graph_json: dict):
        """Compile workflow JSON into a LangGraph CompiledGraph."""
        graph = StateGraph(WorkflowState)

        # Add nodes
        for node_def in graph_json["nodes"]:
            node_cls = node_registry.get(node_def["type"])
            config = node_def.get("data", {})
            config["id"] = node_def["id"]
            node_instance = node_cls(config=config)
            handler = self._make_handler(node_instance)
            graph.add_node(node_def["id"], handler)

        # Set entry point to the first node in topological order
        order = self.topological_sort(graph_json)
        if not order:
            raise ValueError("Workflow graph has no nodes")
        graph.set_entry_point(order[0])

        # Add edges
        for edge in graph_json["edges"]:
            graph.add_edge(edge["source"], edge["target"])

        # Set finish point to the last node in topological order
        graph.set_finish_point(order[-1])

        return graph.compile()
