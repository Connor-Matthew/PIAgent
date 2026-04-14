from abc import ABC, abstractmethod
from typing import Any

from backend.core.state import WorkflowState


class BaseNode(ABC):
    node_type: str = ""

    def __init_subclass__(cls, **kwargs):
        super().__init_subclass__(**kwargs)
        if not cls.node_type:
            raise ValueError(f"{cls.__name__} must define a non-empty node_type")

    def __init__(self, config: dict[str, Any] | None = None):
        self.config = config or {}

    @property
    def node_id(self) -> str:
        return self.config.get("id", self.node_type)

    @abstractmethod
    async def execute(self, state: WorkflowState, **kwargs) -> WorkflowState:
        ...
