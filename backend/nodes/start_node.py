from backend.nodes.base import BaseNode
from backend.core.state import WorkflowState


class StartNode(BaseNode):
    node_type = "start"

    async def execute(self, state: WorkflowState, **kwargs) -> WorkflowState:
        user_input = kwargs.get("user_input", state.get("input", ""))
        state["input"] = user_input
        state["node_outputs"]["start"] = {"input": user_input}
        return state
