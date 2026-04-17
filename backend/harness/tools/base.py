from __future__ import annotations

from typing import Protocol, runtime_checkable

from pydantic import BaseModel


@runtime_checkable
class Tool(Protocol):
    name: str
    input_schema: type[BaseModel]
    output_schema: type[BaseModel]
    side_effects: bool = False

    async def run(self, args: BaseModel) -> BaseModel:
        ...
