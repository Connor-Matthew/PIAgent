from abc import ABC, abstractmethod
from backend.core.state import WorkflowState


class BaseNode(ABC):
    node_type: str = ""

    def __init__(self, config: dict | None = None):
        self.config = config or {}

    @abstractmethod
    async def execute(self, state: WorkflowState) -> WorkflowState:
        ...
