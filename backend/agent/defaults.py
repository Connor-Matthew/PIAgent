from backend.agent.schemas import RecipeIR


DEFAULT_LLM_MODEL_BY_TYPE: dict[str, str] = {
    "openai": "gpt-4o",
    "anthropic": "claude-3-5-sonnet-latest",
    "google": "gemini-2.0-flash",
    "deepseek": "deepseek-chat",
    "openai_compatible": "gpt-4o-mini",
}

DEFAULT_TTS_VOICES_BY_TYPE: dict[str, list[str]] = {
    "fish_audio": ["default"],
    "minimax_tts": ["male-qn-qingse", "female-shaonv"],
}

DEFAULT_NODE_POSITIONS: dict[str, dict[str, int]] = {
    "start_1": {"x": 80, "y": 240},
    "rag_1": {"x": 320, "y": 240},
    "llm_1": {"x": 560, "y": 240},
    "tts_1": {"x": 800, "y": 240},
    "end_1": {"x": 1040, "y": 240},
}


def resolve_default_llm_model(
    provider_type: str,
    selected_models: list[str] | None = None,
    cached_models: list[str] | None = None,
) -> str:
    if selected_models:
        return selected_models[0]
    if cached_models:
        return cached_models[0]
    return DEFAULT_LLM_MODEL_BY_TYPE.get(provider_type, "gpt-4o")


def resolve_default_tts_voices(
    provider_type: str,
    extra_config: dict | None = None,
) -> list[str]:
    extra_config = extra_config or {}
    configured = extra_config.get("voices")
    if isinstance(configured, list):
        voices = [voice for voice in configured if isinstance(voice, str) and voice]
        if voices:
            return voices
    return DEFAULT_TTS_VOICES_BY_TYPE.get(provider_type, ["default"])


def build_llm_system_prompt(recipe_ir: RecipeIR) -> str:
    audience_map = {
        "general": "Use plain language suitable for a general audience.",
        "general_tech": "Use accessible language for a broad technical audience.",
        "undergraduate_cs": "Explain concepts for computer science undergraduates.",
        "advanced": "Assume an advanced technical audience.",
    }
    tone_map = {
        "neutral_explanatory": "Keep the tone neutral and explanatory.",
        "casual_educational": "Keep the tone approachable and educational.",
        "serious_technical": "Keep the tone precise and technical.",
    }
    format_line = (
        "Write the script as a two-speaker dialogue in one continuous text."
        if recipe_ir.script_format == "dialogue"
        else "Write the script as a single-speaker narration."
    )
    code_line = (
        "Include short, spoken-friendly code explanations where useful."
        if recipe_ir.include_code_snippets
        else "Do not force code examples unless they are necessary for clarity."
    )
    audio_line = (
        "Make the script natural for text-to-speech delivery."
        if recipe_ir.need_audio_output
        else "Focus on producing a readable script."
    )

    prompt_lines = [
        "You are writing the primary script for a PIAgent workflow.",
        f"Goal: {recipe_ir.goal_summary}",
        f"Target length: about {recipe_ir.duration_minutes} minutes.",
        audience_map[recipe_ir.audience_level],
        tone_map[recipe_ir.tone],
        format_line,
        code_line,
        audio_line,
        "Return only the script body without extra commentary.",
    ]
    return "\n".join(prompt_lines)


def make_node_data(
    *,
    node_type: str,
    label: str,
    config: dict,
    locked: bool = False,
) -> dict:
    return {
        "label": label,
        "nodeType": node_type,
        "locked": locked,
        **config,
    }
