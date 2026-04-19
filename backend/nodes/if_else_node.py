from typing import Any

from backend.nodes.base import BaseNode
from backend.core.state import WorkflowState
from backend.core.template import REF_RE, resolve_reference, render_template


class IfElseNode(BaseNode):
    node_type = "if_else"

    async def execute(self, state: WorkflowState, **kwargs) -> WorkflowState:
        # Scheduling and evaluation are handled by the engine.
        return state

    @staticmethod
    def _resolve_value(value: str, state: WorkflowState) -> Any:
        """Resolve a value according to typed-reference rules:
        - Full template reference (e.g. {{node.field}}) → resolve_reference, preserve type
        - Mixed template (e.g. "Score: {{node.score}}") → render_template, result is string
        - Plain literal → return as-is
        """
        if REF_RE.fullmatch(value):
            return resolve_reference(value, state)
        if "{{" in value:
            return render_template(value, state)
        return value

    @staticmethod
    def evaluate_condition(condition: dict, state: WorkflowState) -> bool:
        op = condition["op"]

        if op in ("is_empty", "is_not_empty"):
            left_val = IfElseNode._resolve_value(condition.get("left", ""), state)
            is_empty = left_val is None or left_val == "" or left_val == [] or left_val == {}
            return is_empty if op == "is_empty" else not is_empty

        left_val = IfElseNode._resolve_value(condition["left"], state)
        right_val = IfElseNode._resolve_value(condition["right"], state)

        if op == "eq":
            return left_val == right_val
        if op == "ne":
            return left_val != right_val
        if op == "contains":
            if isinstance(left_val, str) and isinstance(right_val, str):
                return right_val in left_val
            if isinstance(left_val, (list, tuple)):
                return right_val in left_val
            if isinstance(left_val, dict):
                return right_val in left_val
            raise ValueError(
                f"contains operator requires string/list/dict on left, got {type(left_val)}"
            )
        if op == "not_contains":
            if isinstance(left_val, str) and isinstance(right_val, str):
                return right_val not in left_val
            if isinstance(left_val, (list, tuple)):
                return right_val not in left_val
            if isinstance(left_val, dict):
                return right_val not in left_val
            raise ValueError(
                f"not_contains operator requires string/list/dict on left, got {type(left_val)}"
            )
        if op == "gt":
            try:
                return float(left_val) > float(right_val)
            except (TypeError, ValueError) as e:
                raise ValueError(
                    f"gt operator requires numeric values, got {left_val!r} and {right_val!r}"
                ) from e
        if op == "lt":
            try:
                return float(left_val) < float(right_val)
            except (TypeError, ValueError) as e:
                raise ValueError(
                    f"lt operator requires numeric values, got {left_val!r} and {right_val!r}"
                ) from e

        raise ValueError(f"Unknown condition operator: {op}")
