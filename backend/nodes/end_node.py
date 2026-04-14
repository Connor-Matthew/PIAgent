from backend.nodes.base import BaseNode
from backend.core.state import WorkflowState
from backend.core.template import resolve_reference, render_template


class EndNode(BaseNode):
    node_type = "end"

    async def execute(self, state: WorkflowState, **kwargs) -> WorkflowState:
        outputs_config = self.config.get("outputs", [])
        answer_template = self.config.get("answer", "")

        outputs = {}
        for out in outputs_config:
            name = out["name"]
            source = out.get("source", "input")
            value = out.get("value", "")
            if source == "reference":
                outputs[name] = resolve_reference(value, state)
            else:
                outputs[name] = value

        answer = render_template(answer_template, state, local_vars=outputs)

        state["outputs"] = outputs
        state["answer"] = answer
        state.setdefault("node_outputs", {})
        state["node_outputs"][self.node_id] = {
            "outputs": outputs,
            "answer": answer,
        }
        return state
