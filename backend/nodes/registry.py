from backend.nodes.base import BaseNode


class NodeRegistry:
    def __init__(self):
        self._registry: dict[str, type[BaseNode]] = {}

    def register(self, node_cls: type[BaseNode]):
        self._registry[node_cls.node_type] = node_cls

    def get(self, node_type: str) -> type[BaseNode]:
        if node_type not in self._registry:
            raise KeyError(f"Unknown node type: {node_type}")
        return self._registry[node_type]

    def list_types(self) -> list[str]:
        return list(self._registry.keys())


# Global registry instance
node_registry = NodeRegistry()
