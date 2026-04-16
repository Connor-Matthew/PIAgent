from unittest.mock import patch

from backend.agent.planner import AgentPlanner
from backend.agent.schemas import RecipeIR
from backend.core.crypto import encrypt
from backend.models.provider import Provider


def _add_llm_provider(db):
    provider = Provider(
        type="openai",
        category="llm",
        name="Planner OpenAI",
        api_key_encrypted=encrypt("sk-test"),
        enabled=True,
    )
    db.add(provider)
    db.commit()
    db.refresh(provider)
    return provider


def _invalid_tts_recipe(provider_id: int) -> RecipeIR:
    return RecipeIR(
        recipe="start_llm_tts_end",
        goal_summary="生成播客脚本",
        audience_level="general_tech",
        tone="casual_educational",
        duration_minutes=10,
        script_format="monologue",
        include_code_snippets=False,
        use_knowledge_base=False,
        need_audio_output=True,
        llm_provider_id=provider_id,
        tts_provider_id=999,
        tts_voice_id="ghost-voice",
    )


def _valid_text_recipe(provider_id: int) -> RecipeIR:
    return RecipeIR(
        recipe="start_llm_end",
        goal_summary="生成播客脚本",
        audience_level="general_tech",
        tone="casual_educational",
        duration_minutes=10,
        script_format="monologue",
        include_code_snippets=False,
        use_knowledge_base=False,
        need_audio_output=False,
        llm_provider_id=provider_id,
    )


def test_planner_repairs_invalid_recipe_before_fallback(db):
    provider = _add_llm_provider(db)
    planner = AgentPlanner(db)

    with patch.object(planner.generator, "generate", return_value=_invalid_tts_recipe(provider.id)), patch.object(
        planner.generator, "repair", return_value=_valid_text_recipe(provider.id)
    ) as repair_mock:
        draft = planner.plan_default("做一期播客")

    assert draft.recipe_ir.recipe == "start_llm_end"
    assert draft.defaults_applied is False
    assert any(event["type"] == "recipe_repairing" for event in draft.events)
    repair_mock.assert_called_once()


def test_planner_falls_back_after_repair_attempts_are_exhausted(db):
    provider = _add_llm_provider(db)
    planner = AgentPlanner(db)

    with patch.object(planner.generator, "generate", return_value=_invalid_tts_recipe(provider.id)), patch.object(
        planner.generator,
        "repair",
        side_effect=[
            _invalid_tts_recipe(provider.id),
            _invalid_tts_recipe(provider.id),
        ],
    ):
        draft = planner.plan_default("做一期播客")

    assert draft.defaults_applied is True
    assert draft.recipe_ir.recipe == "start_llm_end"
    assert any(event["type"] == "recipe_fallback" for event in draft.events)
