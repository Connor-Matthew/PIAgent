import json


def build_clarifier_system_prompt(max_turns: int) -> str:
    return "\n".join(
        [
            "You are the clarification planner for PIAgent.",
            "Your only job is to decide whether one more clarification question is still necessary before recipe generation.",
            "Only ask about dimensions that materially change the current workflow recipe.",
            "Ask at most one dimension per round.",
            f"Never exceed {max_turns} clarification turns.",
            "If defaults are already sufficient, set need_more_info=false.",
            "Questions must be written in natural Chinese.",
            "Return only structured output that matches the provided schema.",
        ]
    )


def build_clarifier_user_prompt(
    *,
    goal: str,
    answered_dims: dict,
    turns: list[dict],
    allowed_dims: list[str],
    capabilities_summary: dict,
) -> str:
    return "\n".join(
        [
            f"Goal: {goal}",
            f"Already answered dimensions: {json.dumps(answered_dims, ensure_ascii=False)}",
            f"Clarification turns so far: {json.dumps(turns, ensure_ascii=False)}",
            f"Allowed dimensions: {json.dumps(allowed_dims, ensure_ascii=False)}",
            f"Runtime capabilities: {json.dumps(capabilities_summary, ensure_ascii=False)}",
            "If defaults are good enough, set need_more_info=false.",
            "If you ask another question, choose exactly one next_dim from the allowed list.",
        ]
    )


def build_generator_system_prompt() -> str:
    return "\n".join(
        [
            "You are the workflow recipe generator for PIAgent.",
            "Do not generate an arbitrary DAG.",
            "The current runtime phase only supports recipe expansion over start, rag, llm, tts, and end nodes.",
            "Choose one supported recipe and fill a RecipeIR object that fits the user's goal and the runtime capabilities.",
            "Prefer the simplest valid recipe that satisfies the goal.",
            "Do not invent recipe literals, provider IDs, voice IDs, or knowledge base IDs.",
            "Return only structured output that matches the provided schema.",
        ]
    )


def build_generator_user_prompt(
    *,
    goal: str,
    answered_dims: dict,
    supported_recipes: list[str],
    capabilities_summary: dict,
    heuristic_defaults: dict,
) -> str:
    return "\n".join(
        [
            f"Goal: {goal}",
            f"Answered dimensions: {json.dumps(answered_dims, ensure_ascii=False)}",
            f"Supported recipes: {json.dumps(supported_recipes, ensure_ascii=False)}",
            f"Runtime capabilities: {json.dumps(capabilities_summary, ensure_ascii=False)}",
            f"Heuristic defaults: {json.dumps(heuristic_defaults, ensure_ascii=False)}",
            "Use runtime IDs exactly as provided.",
            "If audio is not needed or unavailable, do not select a TTS recipe.",
            "If knowledge base usage is not needed or unavailable, do not select a RAG recipe.",
        ]
    )


def build_copywriter_system_prompt() -> str:
    return "\n".join(
        [
            "你是 PIAgent 的文案策划。你要为一张已经确定形态的 workflow 草案写两段文字。",
            "1. system_prompt：给 workflow 中的 llm 节点使用的系统提示词，必须针对本次目标量身定制，体现受众、语气、结构与长度要求，避免通用套话。",
            "2. rationale：用一到两句中文向终端用户解释为什么这样规划，要具体提及是否使用知识库、是否合成音频，并与用户目标呼应。",
            "只输出符合 schema 的 JSON。system_prompt 使用英文以稳定下游模型；rationale 使用中文。",
        ]
    )


def build_copywriter_user_prompt(
    *,
    goal: str,
    recipe_ir: dict,
    capabilities_summary: dict,
) -> str:
    return "\n".join(
        [
            f"用户原始目标: {goal}",
            f"已确定的 RecipeIR: {json.dumps(recipe_ir, ensure_ascii=False)}",
            f"运行时能力: {json.dumps(capabilities_summary, ensure_ascii=False)}",
            "system_prompt 要能让 llm 节点直接写出成品脚本，无需再追加规则。",
            "rationale 禁止复述字段名，禁止使用 最低风险 这类空话，要让用户能一眼看懂链路意图。",
        ]
    )


def build_generator_repair_user_prompt(
    *,
    goal: str,
    answered_dims: dict,
    supported_recipes: list[str],
    capabilities_summary: dict,
    heuristic_defaults: dict,
    attempt: int,
    previous_recipe: dict | None,
    errors: list[str],
) -> str:
    return "\n".join(
        [
            f"Goal: {goal}",
            f"Answered dimensions: {json.dumps(answered_dims, ensure_ascii=False)}",
            f"Supported recipes: {json.dumps(supported_recipes, ensure_ascii=False)}",
            f"Runtime capabilities: {json.dumps(capabilities_summary, ensure_ascii=False)}",
            f"Heuristic defaults: {json.dumps(heuristic_defaults, ensure_ascii=False)}",
            f"Repair attempt: {attempt}",
            f"Previous invalid recipe: {json.dumps(previous_recipe, ensure_ascii=False)}",
            f"Validation errors: {json.dumps(errors, ensure_ascii=False)}",
            "Repair the RecipeIR so it becomes valid for the current runtime.",
            "Use runtime IDs exactly as provided.",
            "Do not keep any field that conflicts with the selected recipe.",
            "Return only a corrected RecipeIR JSON object.",
        ]
    )
