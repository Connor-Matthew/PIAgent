import re
from typing import Any

from backend.core.state import WorkflowState

REF_RE = re.compile(r"\{\{\s*([a-zA-Z_][\w]*)(?:\.([a-zA-Z_][\w]*))?\s*\}\}")


def resolve_reference(token: str, state: WorkflowState, local_vars: dict | None = None) -> Any:
    """解析单个 {{x}} 或 {{x.y}}，未命中返回空字符串。

    支持 iteration 上下文变量（item / index）优先解析。
    """
    match = REF_RE.match(token)
    if not match:
        return ""

    part1 = match.group(1)
    part2 = match.group(2)
    local_vars = local_vars or {}

    # 1. 先查 _iter_context（iteration 当前项 / 索引）
    iter_context = state.get("_iter_context")
    if iter_context:
        item_var = iter_context.get("itemVar", "item")
        index_var = iter_context.get("indexVar", "index")
        if part1 == item_var:
            value = iter_context["item"]
            if part2 is not None:
                if isinstance(value, dict):
                    return value.get(part2, "")
                if isinstance(value, (list, tuple)) and part2.isdigit():
                    try:
                        return value[int(part2)]
                    except (IndexError, ValueError):
                        return ""
            return value if value is not None else ""
        if part1 == index_var:
            value = iter_context["index"]
            return value if value is not None else ""

    # 2. {{nodeId.fieldName}} — 查 state["node_outputs"]
    if part2 is not None:
        node_outputs = state.get("node_outputs", {})
        node_out = node_outputs.get(part1, {})
        value = node_out.get(part2)
        return value if value is not None else ""

    # 3. {{varName}} — 先查 local_vars（End 节点自身的 outputs）
    if part1 in local_vars:
        value = local_vars[part1]
        return value if value is not None else ""

    # 4. 再查 state["inputs"]
    inputs = state.get("inputs", {})
    if part1 in inputs:
        value = inputs[part1]
        return value if value is not None else ""

    return ""


def render_template(template: str, state: WorkflowState, local_vars: dict | None = None) -> str:
    """把模板里所有 {{...}} 替换成字符串。"""

    def replacer(match: re.Match) -> str:
        value = resolve_reference(match.group(0), state, local_vars)
        return str(value) if value is not None else ""

    return REF_RE.sub(replacer, template)
