from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Protocol, runtime_checkable

from pydantic import BaseModel
from sqlalchemy.orm import Session


@dataclass
class HarnessContext:
    """Lightweight runtime context for harness tools."""

    db: Session | None = None


class EmptyToolInput(BaseModel):
    """Explicit empty input schema for read-only tools that take no arguments."""


@runtime_checkable
class Tool(Protocol):
    """Protocol for a harness tool.

    Each tool is self-describing via Pydantic schemas and exposes an async
    ``run`` entrypoint.  Tools with ``side_effects=True`` may be skipped in
    dry-run mode (reserved for future use).
    """

    name: str
    description: str
    input_schema: type[BaseModel]
    output_schema: type[BaseModel]
    side_effects: bool

    async def run(self, args: BaseModel, ctx: HarnessContext) -> BaseModel:
        ...


class ToolRegistry:
    """Registry for harness tools."""

    def __init__(self) -> None:
        self._registry: dict[str, Tool] = {}

    def register(self, tool: Tool) -> None:
        if not tool.name:
            raise ValueError("Tool must define a non-empty name")
        if tool.name in self._registry:
            raise KeyError(f"Tool '{tool.name}' is already registered")
        self._registry[tool.name] = tool

    def get(self, name: str) -> Tool:
        if name not in self._registry:
            raise KeyError(f"Unknown tool: {name}")
        return self._registry[name]

    def list_tools(self) -> list[Tool]:
        return list(self._registry.values())

    def render_catalog(self) -> str:
        """Render a catalog of all registered tools for use in system prompts."""
        lines: list[str] = []
        lines.append("# Available Tools")
        lines.append("")
        for tool in self._registry.values():
            lines.append(f"## {tool.name}")
            lines.append(f"{tool.description}")
            lines.append("")
            lines.append("### Input Schema")
            lines.append(
                json.dumps(
                    tool.input_schema.model_json_schema(),
                    ensure_ascii=False,
                    indent=2,
                )
            )
            lines.append("")
        return "\n".join(lines)
