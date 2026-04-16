import pytest
from pydantic import ValidationError

from backend.agent.schemas import ClarifyDecision, RecipeIR


def test_clarify_decision_requires_next_fields_when_follow_up_needed():
    with pytest.raises(ValidationError, match="next_dim is required"):
        ClarifyDecision(
            need_more_info=True,
            next_question="还需要什么？",
            rationale="还缺一个关键维度",
        )


def test_recipe_ir_rejects_inconsistent_recipe_flags():
    with pytest.raises(ValidationError, match="need_audio_output must match"):
        RecipeIR(
            recipe="start_llm_end",
            goal_summary="生成一段脚本",
            audience_level="general_tech",
            tone="casual_educational",
            duration_minutes=10,
            script_format="monologue",
            include_code_snippets=False,
            use_knowledge_base=False,
            need_audio_output=True,
        )


def test_recipe_ir_rejects_tts_fields_when_audio_disabled():
    with pytest.raises(
        ValidationError,
        match="tts_provider_id and tts_voice_id must be null",
    ):
        RecipeIR(
            recipe="start_llm_end",
            goal_summary="生成一段脚本",
            audience_level="general_tech",
            tone="casual_educational",
            duration_minutes=10,
            script_format="monologue",
            include_code_snippets=False,
            use_knowledge_base=False,
            need_audio_output=False,
            tts_provider_id=2,
            tts_voice_id="voice",
        )
