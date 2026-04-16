from unittest.mock import patch

from backend.agent.capabilities import load_capabilities
from backend.agent.clarifier import AgentClarifier
from backend.agent.planner import AgentPlanner
from backend.agent.schemas import ClarifyDecision, RecipeIR
from backend.core.crypto import encrypt
from backend.models.provider import Provider


def _add_llm_provider(db):
    provider = Provider(
        type="openai",
        category="llm",
        name="Agent Test OpenAI",
        api_key_encrypted=encrypt("sk-test"),
        enabled=True,
    )
    db.add(provider)
    db.commit()
    db.refresh(provider)
    return provider


def test_clarifier_uses_llm_structured_output_when_available(db):
    _add_llm_provider(db)
    tts_provider = Provider(
        type="minimax_tts",
        category="tts",
        name="Agent Test TTS",
        api_key_encrypted=encrypt("tts-test"),
        enabled=True,
        extra_config={"voices": ["female-shaonv"]},
    )
    db.add(tts_provider)
    db.commit()
    capabilities = load_capabilities(db)
    clarifier = AgentClarifier(db)

    with patch(
        "backend.agent.clarifier.AgentLLMClient.structured_invoke",
        return_value=ClarifyDecision(
            need_more_info=True,
            next_dim="need_audio_output",
            next_question="你是希望直接生成音频，还是只要脚本文本？",
            rationale="是否生成音频会改变草案是否含 tts 节点",
        ),
    ) as mock_invoke:
        decision = clarifier.decide(
            goal="给我整理一份 Transformer 内容",
            answered_dims={},
            turns=[],
            capabilities=capabilities,
        )

    assert decision.next_dim == "need_audio_output"
    mock_invoke.assert_called_once()


def test_planner_uses_llm_recipe_when_available(db):
    provider = _add_llm_provider(db)
    planner = AgentPlanner(db)

    with patch(
        "backend.agent.generator.AgentLLMClient.structured_invoke",
        return_value=RecipeIR(
            recipe="start_llm_end",
            goal_summary="生成一份注意力机制讲稿",
            audience_level="general_tech",
            tone="neutral_explanatory",
            duration_minutes=8,
            script_format="monologue",
            include_code_snippets=False,
            use_knowledge_base=False,
            need_audio_output=False,
            llm_provider_id=provider.id,
        ),
    ) as mock_invoke:
        draft = planner.plan_default("给我一份注意力机制讲稿，不需要音频")

    assert draft.recipe_ir.recipe == "start_llm_end"
    assert draft.recipe_ir.duration_minutes == 8
    mock_invoke.assert_called_once()


def test_planner_falls_back_to_heuristic_when_llm_generation_fails(db):
    _add_llm_provider(db)
    planner = AgentPlanner(db)

    with patch(
        "backend.agent.generator.AgentLLMClient.structured_invoke",
        side_effect=RuntimeError("llm failed"),
    ):
        draft = planner.plan_default("做一期播客")

    assert draft.recipe_ir.recipe in {"start_llm_end", "start_llm_tts_end"}
