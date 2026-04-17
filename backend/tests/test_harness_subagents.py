import pytest

from backend.agent.capabilities import (
    AgentCapabilities,
    KnowledgeBaseCapability,
    LLMProviderCapability,
    TTSProviderCapability,
)
from backend.agent.llm import AgentLLMDisabledError
from backend.harness.schemas import CapabilityScoutReport, RecipeChallengerReport
from backend.harness.subagents.capability_scout import CapabilityScoutAgent
from backend.harness.validators import GraphStructureValidator
from backend.harness.subagents.recipe_challenger import RecipeChallengerAgent


@pytest.mark.asyncio
async def test_graph_structure_finds_no_risks_in_valid_graph():
    graph = {
        "nodes": [
            {"id": "start_1", "type": "start", "data": {"inputs": []}},
            {"id": "llm_1", "type": "llm", "data": {"provider_id": 1}},
            {"id": "end_1", "type": "end", "data": {"outputs": []}},
        ],
        "edges": [
            {"source": "start_1", "target": "llm_1"},
            {"source": "llm_1", "target": "end_1"},
        ],
    }
    agent = GraphStructureValidator()
    report = await agent.analyze({"graph": graph})

    assert report.agent_name == "graph_structure"
    assert report.observations
    critic_report = report.observations[0]
    assert critic_report["score"] == 100
    assert critic_report["risks"] == []


@pytest.mark.asyncio
async def test_graph_structure_detects_missing_nodes_and_isolated_nodes():
    graph = {
        "nodes": [
            {"id": "start_1", "type": "start", "data": {"inputs": []}},
            {"id": "llm_1", "type": "llm", "data": {"provider_id": 1}},
            {"id": "orphan", "type": "llm", "data": {"provider_id": 1}},
        ],
        "edges": [
            {"source": "start_1", "target": "llm_1"},
        ],
    }
    agent = GraphStructureValidator()
    report = await agent.analyze({"graph": graph})

    assert report.agent_name == "graph_structure"
    critic_report = report.observations[0]
    assert critic_report["score"] < 100
    messages = {r["message"] for r in critic_report["risks"]}
    assert any("孤立节点" in m for m in messages)
    assert any("缺少 end 节点" in m for m in messages)


@pytest.mark.asyncio
async def test_graph_structure_detects_dangling_edges():
    graph = {
        "nodes": [
            {"id": "start_1", "type": "start", "data": {"inputs": []}},
        ],
        "edges": [
            {"source": "start_1", "target": "missing_node"},
        ],
    }
    agent = GraphStructureValidator()
    report = await agent.analyze({"graph": graph})

    critic_report = report.observations[0]
    assert critic_report["score"] < 100
    messages = {r["message"] for r in critic_report["risks"]}
    assert any("missing_node" in m for m in messages)


class FakeLLMForScout:
    def __init__(self, report: CapabilityScoutReport):
        self.report = report

    def structured_invoke(self, *, schema, system_prompt, user_prompt, provider_id=None):
        return self.report


@pytest.mark.asyncio
async def test_capability_scout_uses_llm_when_available():
    capabilities = AgentCapabilities(
        llm_providers=[LLMProviderCapability(id=1, type="openai", name="OpenAI", default_model="gpt-4o")],
    )
    expected = CapabilityScoutReport(
        recommendations=[{"category": "llm", "choice": "OpenAI", "reason": "最佳 LLM"}],
        reasoning="推荐使用 OpenAI",
        warnings=[],
    )
    agent = CapabilityScoutAgent(llm=FakeLLMForScout(expected))
    report = await agent.analyze({"goal": "写一个脚本", "capabilities": capabilities})

    assert report.agent_name == "capability_scout"
    assert report.observations[0]["reasoning"] == "推荐使用 OpenAI"


@pytest.mark.asyncio
async def test_capability_scout_falls_back_to_rules_when_llm_disabled():
    capabilities = AgentCapabilities(
        llm_providers=[LLMProviderCapability(id=1, type="openai", name="OpenAI", default_model="gpt-4o")],
        tts_providers=[TTSProviderCapability(id=2, type="minimax", name="MiniMax", voices=["voice_A"])],
        knowledge_bases=[KnowledgeBaseCapability(id="kb1", name="TestKB", doc_count=5)],
    )

    class DisabledLLM:
        def structured_invoke(self, *, schema, system_prompt, user_prompt, provider_id=None):
            raise AgentLLMDisabledError("disabled")

    agent = CapabilityScoutAgent(llm=DisabledLLM())
    report = await agent.analyze({"goal": "写一个脚本", "capabilities": capabilities})

    assert report.agent_name == "capability_scout"
    obs = report.observations[0]
    assert any(r["category"] == "llm" for r in obs["recommendations"])
    assert any(r["category"] == "tts" for r in obs["recommendations"])
    assert any(r["category"] == "kb" for r in obs["recommendations"])


class FakeLLMForChallenger:
    def __init__(self, report: RecipeChallengerReport):
        self.report = report

    def structured_invoke(self, *, schema, system_prompt, user_prompt, provider_id=None):
        return self.report


@pytest.mark.asyncio
async def test_recipe_challenger_uses_llm_when_available():
    recipe_ir = {"recipe": "start_llm_end", "llm_provider_id": 1}
    expected = RecipeChallengerReport(
        score=90,
        concerns=["缺少 TTS"],
        alternatives=["考虑 start_llm_tts_end"],
        reasoning="方案可行但可改进",
    )
    agent = RecipeChallengerAgent(llm=FakeLLMForChallenger(expected))
    report = await agent.analyze({"goal": "写一个脚本并转成音频", "recipe_ir": recipe_ir})

    assert report.agent_name == "recipe_challenger"
    assert report.observations[0]["score"] == 90


@pytest.mark.asyncio
async def test_recipe_challenger_falls_back_to_rules_when_llm_disabled():
    recipe_ir = {"recipe": "start_llm_end", "llm_provider_id": 1}

    class DisabledLLM:
        def structured_invoke(self, *, schema, system_prompt, user_prompt, provider_id=None):
            raise AgentLLMDisabledError("disabled")

    agent = RecipeChallengerAgent(llm=DisabledLLM())
    report = await agent.analyze({"goal": "写一个脚本并转成音频", "recipe_ir": recipe_ir})

    assert report.agent_name == "recipe_challenger"
    obs = report.observations[0]
    assert obs["score"] < 100
    assert any("音频" in c for c in obs["concerns"])
