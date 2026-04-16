import pytest

from backend.agent.adapter import WorkflowGraphAdapter
from backend.agent.capabilities import (
    AgentCapabilities,
    KnowledgeBaseCapability,
    LLMProviderCapability,
    TTSProviderCapability,
)
from backend.agent.schemas import RecipeIR
from backend.agent.validator import RecipeValidationError


def test_adapter_builds_start_llm_end_graph():
    capabilities = AgentCapabilities(
        llm_providers=[
            LLMProviderCapability(
                id=1,
                type="openai",
                name="OpenAI",
                default_model="gpt-4o",
            )
        ]
    )
    recipe_ir = RecipeIR(
        recipe="start_llm_end",
        goal_summary="写一段关于注意力机制的讲稿",
        audience_level="general_tech",
        tone="neutral_explanatory",
        duration_minutes=8,
        script_format="monologue",
        include_code_snippets=False,
        use_knowledge_base=False,
        need_audio_output=False,
        llm_provider_id=1,
    )

    graph = WorkflowGraphAdapter(capabilities).build_graph(recipe_ir)

    assert [node["type"] for node in graph["nodes"]] == ["start", "llm", "end"]
    assert graph["edges"] == [
        {"source": "start_1", "target": "llm_1"},
        {"source": "llm_1", "target": "end_1"},
    ]
    assert graph["nodes"][1]["data"]["provider_id"] == 1
    assert graph["nodes"][2]["data"]["outputs"][0]["value"] == "{{llm_1.text}}"


def test_adapter_builds_start_rag_llm_tts_end_graph():
    capabilities = AgentCapabilities(
        llm_providers=[
            LLMProviderCapability(
                id=1,
                type="openai",
                name="OpenAI",
                default_model="gpt-4o",
            )
        ],
        tts_providers=[
            TTSProviderCapability(
                id=2,
                type="minimax_tts",
                name="MiniMax",
                voices=["male-qn-qingse", "female-shaonv"],
            )
        ],
        knowledge_bases=[
            KnowledgeBaseCapability(
                id="kb_transformer",
                name="Transformer 资料库",
                doc_count=10,
            )
        ],
    )
    recipe_ir = RecipeIR(
        recipe="start_rag_llm_tts_end",
        goal_summary="做一期 Transformer 科普播客",
        audience_level="undergraduate_cs",
        tone="casual_educational",
        duration_minutes=10,
        script_format="monologue",
        include_code_snippets=False,
        use_knowledge_base=True,
        need_audio_output=True,
        knowledge_base_id="kb_transformer",
        llm_provider_id=1,
        tts_provider_id=2,
        tts_voice_id="female-shaonv",
    )

    graph = WorkflowGraphAdapter(capabilities).build_graph(recipe_ir)

    assert [node["type"] for node in graph["nodes"]] == [
        "start",
        "rag",
        "llm",
        "tts",
        "end",
    ]
    assert graph["nodes"][1]["data"]["knowledge_base_id"] == "kb_transformer"
    assert graph["nodes"][3]["data"]["voice_id"] == "female-shaonv"
    outputs = graph["nodes"][4]["data"]["outputs"]
    assert any(output["value"] == "{{tts_1.audio_url}}" for output in outputs)


def test_validator_rejects_unknown_tts_voice():
    capabilities = AgentCapabilities(
        llm_providers=[
            LLMProviderCapability(
                id=1,
                type="openai",
                name="OpenAI",
                default_model="gpt-4o",
            )
        ],
        tts_providers=[
            TTSProviderCapability(
                id=2,
                type="minimax_tts",
                name="MiniMax",
                voices=["male-qn-qingse"],
            )
        ],
    )
    recipe_ir = RecipeIR(
        recipe="start_llm_tts_end",
        goal_summary="做一期播客",
        audience_level="general_tech",
        tone="casual_educational",
        duration_minutes=10,
        script_format="monologue",
        include_code_snippets=False,
        use_knowledge_base=False,
        need_audio_output=True,
        llm_provider_id=1,
        tts_provider_id=2,
        tts_voice_id="female-shaonv",
    )

    with pytest.raises(RecipeValidationError, match="voice_id 'female-shaonv'"):
        WorkflowGraphAdapter(capabilities).build_graph(recipe_ir)
