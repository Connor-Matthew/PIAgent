from __future__ import annotations

from typing import Any

from langchain_core.tools import BaseTool


class ToolRegistry:
    """Minimal runtime-local registry for vendored pi_harness tools."""

    def __init__(self):
        self._tools: dict[str, BaseTool] = {}

    def register(self, tool: BaseTool) -> None:
        self._tools[tool.name] = tool

    def get(self, name: str) -> BaseTool | None:
        return self._tools.get(name)

    def get_tools(self, names: list[str] | None = None) -> list[BaseTool]:
        if names is None:
            return list(self._tools.values())
        return [self._tools[name] for name in names if name in self._tools]

    def list_tools(self) -> list[dict[str, Any]]:
        return [
            {"name": tool.name, "description": tool.description}
            for tool in self._tools.values()
        ]


_tool_registry_instance: ToolRegistry | None = None


def get_tool_registry() -> ToolRegistry:
    global _tool_registry_instance
    if _tool_registry_instance is None:
        _tool_registry_instance = ToolRegistry()
    return _tool_registry_instance
