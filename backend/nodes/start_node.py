from backend.nodes.base import BaseNode
from backend.core.state import WorkflowState


class StartNode(BaseNode):
    node_type = "start"

    async def execute(self, state: WorkflowState, **kwargs) -> WorkflowState:
        # 优先读取结构化的 inputs，兼容旧路径的 user_input / state["input"]
        inputs = state.get("inputs") or {}
        if not inputs:
            fallback = kwargs.get("user_input") or state.get("input", "")
            if fallback:
                inputs = {"input": fallback}

        schema = self.config.get("inputs", [])

        # 校验必填字段
        for field in schema:
            if field.get("required") and field["name"] not in inputs:
                raise ValueError(f"Missing required input field: {field['name']}")

        # 写入 node_outputs
        state.setdefault("node_outputs", {})
        state["node_outputs"][self.node_id] = dict(inputs)

        # 兼容旧路径：若 schema 有 input 字段或只有一个字段，写入 state["input"]
        if inputs:
            if "input" in inputs:
                state["input"] = inputs["input"]
            elif len(schema) == 1:
                state["input"] = inputs.get(schema[0]["name"], "")
            elif len(inputs) == 1:
                state["input"] = list(inputs.values())[0]

        return state
