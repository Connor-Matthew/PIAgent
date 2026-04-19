from backend.nodes.base import BaseNode
from backend.core.state import WorkflowState


class IterationNode(BaseNode):
    node_type = "iteration"

    async def execute(self, state: WorkflowState, **kwargs) -> WorkflowState:
        # Scheduling is handled by the engine.
        return state
