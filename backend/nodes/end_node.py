from backend.nodes.base import BaseNode
from backend.core.state import WorkflowState


class EndNode(BaseNode):
    node_type = "end"

    async def execute(self, state: WorkflowState, **kwargs) -> WorkflowState:
        state["node_outputs"]["end"] = {
            "llm_output": state.get("llm_output", ""),
            "audio_url": state.get("audio_url", ""),
        }
        return state
