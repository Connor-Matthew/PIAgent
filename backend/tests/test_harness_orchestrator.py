import pytest

from backend.agent.capabilities import AgentCapabilities, LLMProviderCapability
from backend.agent.planner import PlannedDraft
from backend.agent.schemas import RecipeIR
from backend.config import settings
from backend.harness.lead_agent import LeadAgent
from backend.harness.memory import HarnessProjectMemoryStore
from backend.harness.orchestrator import HarnessOrchestrator
from backend.harness.registry import HarnessSkillRegistry
from backend.harness.schemas import LeadAgentPlan, PlanStep, ProposeActionDecision, FinalizeDecision, CallToolDecision
from unittest import mock


class FakeCapabilitiesSkill:
    def __init__(self, capabilities: AgentCapabilities):
        self.capabilities = capabilities

    def load(self) -> AgentCapabilities:
        return self.capabilities

    def observe(self, capabilities: AgentCapabilities) -> dict:
        return {
            "type": "planner_observe",
            "name": "load_capabilities",
            "summary": "mock capabilities",
            "counts": {
                "llm_providers": len(capabilities.llm_providers),
                "tts_providers": len(capabilities.tts_providers),
                "knowledge_bases": len(capabilities.knowledge_bases),
            },
        }

    def invoke(self, ctx: dict | None = None):
        from backend.harness.schemas import SkillResult
        return SkillResult(
            name="load_capabilities",
            ok=True,
            value=self.capabilities,
            events=[self.observe(self.capabilities)],
        )


class FakeRecipeSkill:
    def __init__(self, draft: PlannedDraft):
        self.draft = draft
        self.calls: list[str] = []

    def plan_default(self, goal: str) -> PlannedDraft:
        self.calls.append(goal)
        return self.draft

    def invoke(self, *, goal: str, answered_dims: dict | None = None):
        from backend.harness.schemas import SkillResult
        self.calls.append(goal)
        return SkillResult(
            name="draft_recipe",
            ok=True,
            value=self.draft,
            events=[
                {
                    "type": "planner_observe",
                    "name": "plan_recipe",
                    "summary": f"已选择 {self.draft.recipe_ir.recipe} 作为工作流骨架",
                    "recipe": self.draft.recipe_ir.model_dump(),
                }
            ],
        )


class FakeExecutionSkill:
    def __init__(self):
        self.calls: list[dict] = []

    async def run(self, graph, *, user_input="", inputs=None, on_event=None):
        self.calls.append({
            "graph": graph,
            "user_input": user_input,
            "inputs": inputs,
        })
        if on_event is not None:
            await on_event({"type": "workflow_start"})
            await on_event({"type": "workflow_end", "status": "completed", "duration": 0.0, "answer": "", "outputs": {}})
        return {
            "input": user_input,
            "outputs": {},
            "answer": "",
            "node_outputs": {},
        }


class FakeLLMClient:
    def __init__(self, plan: LeadAgentPlan):
        self.plan = plan

    def structured_invoke(self, *, schema, system_prompt, user_prompt, provider_id=None):
        return self.plan


class FailingLLMClient:
    def structured_invoke(self, *, schema, system_prompt, user_prompt, provider_id=None):
        raise RuntimeError("upstream llm failed")


def _draft() -> PlannedDraft:
    recipe_ir = RecipeIR(
        recipe="start_llm_end",
        goal_summary="写一个简短脚本",
        audience_level="general_tech",
        tone="neutral_explanatory",
        duration_minutes=5,
        script_format="monologue",
        include_code_snippets=False,
        use_knowledge_base=False,
        need_audio_output=False,
        llm_provider_id=1,
    )
    graph = {
        "nodes": [
            {"id": "start_1", "type": "start", "data": {"inputs": []}},
            {"id": "llm_1", "type": "llm", "data": {"provider_id": 1, "model": "gpt-4o"}},
            {"id": "end_1", "type": "end", "data": {"outputs": [], "answer": ""}},
        ],
        "edges": [
            {"source": "start_1", "target": "llm_1"},
            {"source": "llm_1", "target": "end_1"},
        ],
    }
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
    return PlannedDraft(
        recipe_ir=recipe_ir,
        graph=graph,
        capabilities=capabilities,
        events=[],
        defaults_applied=False,
        rationale_text="先生成最小可运行工作流",
    )


def _registry() -> tuple[HarnessSkillRegistry, FakeExecutionSkill, FakeRecipeSkill]:
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
    fake_draft = _draft()
    recipe_skill = FakeRecipeSkill(fake_draft)
    execution_skill = FakeExecutionSkill()
    registry = HarnessSkillRegistry(
        capabilities=FakeCapabilitiesSkill(capabilities),
        recipe=recipe_skill,
        graph_validation=type(
            "ValidationProxy",
            (),
            {"validate": staticmethod(lambda graph, db=None: None)},
        )(),
        execution=execution_skill,
    )
    return registry, execution_skill, recipe_skill


def test_orchestrator_routes_goals_by_complexity(db):
    registry, _, _ = _registry()
    orchestrator = HarnessOrchestrator(db, registry=registry, lead_agent=LeadAgent(registry, db=db))

    assert orchestrator.select_route("做一个脚本") == "fast"
    assert orchestrator.select_route("帮我做一期 AI Agent 播客") == "harness"
    assert orchestrator.select_route("简单总结一下") == "fast"
    assert orchestrator.select_route("请帮我做一个完整的知识库播客工作流，包含多轮规划、构图和执行，并输出音频") == "harness"


@pytest.mark.asyncio
async def test_orchestrator_builds_graph_and_executes_it(db):
    registry, execution_skill, recipe_skill = _registry()
    orchestrator = HarnessOrchestrator(db, registry=registry, lead_agent=LeadAgent(registry, db=db), enable_subagents=False)

    events = []

    async def on_event(event):
        events.append(event)

    result = await orchestrator.run("做一个脚本", on_event=on_event)

    assert result.route == "fast"
    assert result.graph["nodes"][1]["id"] == "llm_1"
    assert recipe_skill.calls == ["做一个脚本"]
    assert execution_skill.calls[0]["graph"] == result.graph

    event_types = [event["type"] for event in events]
    assert "planning_start" in event_types
    assert "planning_update" in event_types
    assert "node_added" in event_types
    assert "edge_added" in event_types
    assert "workflow_built" in event_types
    assert "plan_ready" in event_types
    assert "skill_start" in event_types
    assert "skill_end" in event_types
    assert event_types.index("workflow_built") < event_types.index("plan_ready") < event_types.index("workflow_start")
    plan_ready_event = next(event for event in events if event["type"] == "plan_ready")
    assert plan_ready_event["selected_llm"]["name"] == "OpenAI"
    assert plan_ready_event["selected_llm"]["model"] == "gpt-4o"


@pytest.mark.asyncio
async def test_orchestrator_uses_llm_planning_in_harness_path(db, monkeypatch):
    monkeypatch.setattr("backend.config.settings.agent_llm_enabled", True)
    registry, execution_skill, recipe_skill = _registry()

    plan = LeadAgentPlan(
        reasoning="根据目标，需要生成 recipe",
        steps=[
            PlanStep(type="action", action={"kind": "planning_update", "text": "开始 LLM 规划"}),
            PlanStep(type="skill", name="draft_recipe"),
            PlanStep(type="finish"),
        ],
    )
    fake_llm = FakeLLMClient(plan)
    orchestrator = HarnessOrchestrator(
        db,
        registry=registry,
        lead_agent=LeadAgent(registry, db=db, llm=fake_llm),
        enable_subagents=False,
    )

    events = []

    async def on_event(event):
        events.append(event)

    goal = "请帮我做一个完整的知识库播客工作流，包含多轮规划、构图和执行，并输出音频"
    result = await orchestrator.run(goal, on_event=on_event)

    assert result.route == "harness"
    assert recipe_skill.calls == [goal]
    assert execution_skill.calls[0]["graph"] == result.graph

    event_types = [event["type"] for event in events]
    assert "planning_start" in event_types
    assert any(event.get("text") == "开始 LLM 规划" for event in events if event["type"] == "planning_update")
    assert any(event.get("text") == "根据目标，需要生成 recipe" for event in events if event["type"] == "planning_update")
    assert "skill_start" in event_types
    assert "skill_end" in event_types
    assert "workflow_start" in event_types


@pytest.mark.asyncio
async def test_orchestrator_falls_back_to_hardcoded_when_llm_disabled(db, monkeypatch):
    monkeypatch.setattr("backend.config.settings.agent_llm_enabled", False)
    registry, execution_skill, recipe_skill = _registry()
    orchestrator = HarnessOrchestrator(
        db,
        registry=registry,
        lead_agent=LeadAgent(registry, db=db),
        enable_subagents=False,
    )

    events = []

    async def on_event(event):
        events.append(event)

    goal = "请帮我做一个完整的知识库播客工作流，包含多轮规划、构图和执行，并输出音频"
    result = await orchestrator.run(goal, on_event=on_event)

    assert result.route == "harness"
    assert recipe_skill.calls == [goal]
    assert execution_skill.calls[0]["graph"] == result.graph

    event_types = [event["type"] for event in events]
    assert "planning_start" in event_types
    assert "workflow_start" in event_types


@pytest.mark.asyncio
async def test_orchestrator_falls_back_to_hardcoded_when_llm_errors(db, monkeypatch):
    monkeypatch.setattr("backend.config.settings.agent_llm_enabled", True)
    registry, execution_skill, recipe_skill = _registry()
    orchestrator = HarnessOrchestrator(
        db,
        registry=registry,
        lead_agent=LeadAgent(registry, db=db, llm=FailingLLMClient()),
        enable_subagents=False,
    )

    events = []

    async def on_event(event):
        events.append(event)

    goal = "请帮我做一个完整的知识库播客工作流，包含多轮规划、构图和执行，并输出音频"
    result = await orchestrator.run(goal, on_event=on_event)

    assert result.route == "harness"
    assert recipe_skill.calls == [goal]
    assert execution_skill.calls[0]["graph"] == result.graph
    assert "workflow_start" in [event["type"] for event in events]


@pytest.mark.asyncio
async def test_orchestrator_spawns_subagents_and_learns_project_memory(db, monkeypatch):
    monkeypatch.setattr("backend.config.settings.agent_llm_enabled", False)
    registry, execution_skill, recipe_skill = _registry()
    project_store = HarnessProjectMemoryStore(db)
    orchestrator = HarnessOrchestrator(
        db,
        registry=registry,
        lead_agent=LeadAgent(registry, db=db),
        project_memory_store=project_store,
        enable_subagents=True,
    )

    events = []

    async def on_event(event):
        events.append(event)

    goal = "请帮我写一个详细脚本并转成播客音频，需要完整的多轮规划和执行输出"
    result = await orchestrator.run(goal, on_event=on_event)

    assert result.route == "harness"
    event_types = [event["type"] for event in events]
    assert "subagent_spawned" in event_types
    assert "subagent_result" in event_types

    # Verify project memory learned from session
    prefs = project_store.load("default")
    assert prefs is not None
    assert prefs.preferred_llm_provider_id == 1


@pytest.mark.asyncio
async def test_orchestrator_loads_project_memory_when_available(db, monkeypatch):
    monkeypatch.setattr("backend.config.settings.agent_llm_enabled", False)
    registry, _, _ = _registry()
    project_store = HarnessProjectMemoryStore(db)
    prefs = project_store.get_or_create("default")
    prefs.preferred_llm_provider_id = 1
    db.add(prefs)
    db.commit()
    db.refresh(prefs)

    orchestrator = HarnessOrchestrator(
        db,
        registry=registry,
        lead_agent=LeadAgent(registry, db=db),
        project_memory_store=project_store,
        enable_subagents=False,
    )

    events = []

    async def on_event(event):
        events.append(event)

    result = await orchestrator.run("做一个脚本", on_event=on_event)
    assert result.route == "fast"

    memory_event = next((e for e in events if e["type"] == "project_memory_loaded"), None)
    assert memory_event is not None
    assert memory_event["summary"]["preferred_llm_provider"]["id"] == 1


class FakeLoopLLMClient:
    def __init__(self, plan: LeadAgentPlan | None = None):
        self._plan = plan
        self.calls: list[dict] = []

    def structured_invoke(self, *, schema, system_prompt, user_prompt, provider_id=None):
        self.calls.append({"schema": schema, "system_prompt": system_prompt, "user_prompt": user_prompt})
        if schema is LeadAgentPlan and self._plan:
            return self._plan
        raise RuntimeError("no mock configured")


@pytest.mark.asyncio
async def test_loop_disabled_uses_single_shot(db, monkeypatch):
    monkeypatch.setattr("backend.config.settings.agent_llm_enabled", True)
    monkeypatch.setattr("backend.config.settings.harness_loop_enabled", False)
    registry, execution_skill, recipe_skill = _registry()

    plan = LeadAgentPlan(
        reasoning="单次规划",
        steps=[
            PlanStep(type="action", action={"kind": "planning_update", "text": "开始规划"}),
            PlanStep(type="skill", name="draft_recipe"),
            PlanStep(type="finish"),
        ],
    )
    fake_llm = FakeLoopLLMClient(plan=plan)
    orchestrator = HarnessOrchestrator(
        db,
        registry=registry,
        lead_agent=LeadAgent(registry, db=db, llm=fake_llm),
        enable_subagents=False,
    )

    events = []
    async def on_event(event):
        events.append(event)

    goal = "请帮我做一个完整的知识库播客工作流"
    result = await orchestrator.run(goal, on_event=on_event)
    assert result.route == "harness"
    event_types = [e["type"] for e in events]
    assert "lead_step_start" not in event_types
    assert "workflow_built" in event_types
    assert "plan_ready" in event_types


@pytest.mark.asyncio
async def test_loop_multi_step_chain(db, monkeypatch):
    monkeypatch.setattr("backend.config.settings.agent_llm_enabled", True)
    monkeypatch.setattr("backend.config.settings.harness_loop_enabled", True)
    registry, execution_skill, recipe_skill = _registry()

    orchestrator = HarnessOrchestrator(
        db,
        registry=registry,
        lead_agent=LeadAgent(registry, db=db),
        enable_subagents=False,
    )

    events = []
    async def on_event(event):
        events.append(event)

    with mock.patch.object(
        LeadAgent,
        "decide",
        side_effect=[
            ProposeActionDecision(action={"kind": "add_node", "node": {"id": "n1", "type": "start"}}),
            ProposeActionDecision(action={"kind": "commit_graph"}),
            FinalizeDecision(reasoning="完成"),
        ],
    ):
        goal = "请帮我做一个完整的知识库播客工作流"
        result = await orchestrator.run(goal, on_event=on_event)
        assert result.route == "harness"
        assert result.graph is not None

        event_types = [e["type"] for e in events]
        assert event_types.count("lead_step_start") == 3
        assert event_types.count("lead_decision") == 3
        assert event_types.count("lead_observation") == 2
        assert event_types.count("lead_step_end") == 3
        assert "workflow_built" in event_types
        assert "plan_ready" in event_types


@pytest.mark.asyncio
async def test_loop_budget_exceeded(db, monkeypatch):
    monkeypatch.setattr("backend.config.settings.agent_llm_enabled", True)
    monkeypatch.setattr("backend.config.settings.harness_loop_enabled", True)
    monkeypatch.setattr("backend.config.settings.harness_loop_max_steps", 2)
    registry, execution_skill, recipe_skill = _registry()

    from backend.harness.builder import GraphDraftBuilder

    # Avoid validation so we can test force-commit path with an empty graph
    monkeypatch.setattr(GraphDraftBuilder, "_commit_graph", lambda self: setattr(self.draft, "committed", True))

    orchestrator = HarnessOrchestrator(
        db,
        registry=registry,
        lead_agent=LeadAgent(registry, db=db),
        enable_subagents=False,
    )

    events = []
    async def on_event(event):
        events.append(event)

    with mock.patch.object(
        LeadAgent,
        "decide",
        side_effect=[
            ProposeActionDecision(action={"kind": "planning_update", "text": "第1步"}),
            ProposeActionDecision(action={"kind": "planning_update", "text": "第2步"}),
        ],
    ):
        goal = "请帮我做一个完整的知识库播客工作流"
        result = await orchestrator.run(goal, on_event=on_event)
        assert result.route == "harness"
        # Should force commit after budget exceeded
        assert any("强制提交" in str(e.get("text", "")) for e in events)
        assert "workflow_built" in [e["type"] for e in events]
        assert "plan_ready" in [e["type"] for e in events]


@pytest.mark.asyncio
async def test_loop_llm_failure_falls_back(db, monkeypatch):
    monkeypatch.setattr("backend.config.settings.agent_llm_enabled", True)
    monkeypatch.setattr("backend.config.settings.harness_loop_enabled", True)
    registry, execution_skill, recipe_skill = _registry()

    class ExplodingLLM:
        def structured_invoke(self, *, schema, system_prompt, user_prompt, provider_id=None):
            raise RuntimeError("llm exploded")

    orchestrator = HarnessOrchestrator(
        db,
        registry=registry,
        lead_agent=LeadAgent(registry, db=db, llm=ExplodingLLM()),
        enable_subagents=False,
    )

    events = []
    async def on_event(event):
        events.append(event)

    goal = "请帮我做一个完整的知识库播客工作流"
    result = await orchestrator.run(goal, on_event=on_event)
    assert result.route == "harness"
    # Fallback to single-shot plan path
    event_types = [e["type"] for e in events]
    assert "workflow_built" in event_types
    assert "plan_ready" in event_types
    # Should emit fallback marker
    assert any(e.get("fallback") for e in events if e["type"] == "lead_step_end")


@pytest.mark.asyncio
async def test_loop_observation_drives_next_decision(db, monkeypatch):
    monkeypatch.setattr("backend.config.settings.agent_llm_enabled", True)
    monkeypatch.setattr("backend.config.settings.harness_loop_enabled", True)
    registry, execution_skill, recipe_skill = _registry()

    orchestrator = HarnessOrchestrator(
        db,
        registry=registry,
        lead_agent=LeadAgent(registry, db=db),
        enable_subagents=False,
    )

    events = []
    async def on_event(event):
        events.append(event)

    captured_calls = []

    async def patched_decide_with_llm(self, goal, *, route, **kwargs):
        # Copy mutable lists so later mutations don't affect captured snapshot
        captured_calls.append({
            **kwargs,
            "history": list(kwargs["history"]) if kwargs.get("history") is not None else None,
            "tool_results": list(kwargs["tool_results"]) if kwargs.get("tool_results") is not None else None,
        })
        if len(captured_calls) == 1:
            return ProposeActionDecision(action={"kind": "planning_update", "text": "第1步"})
        return FinalizeDecision(reasoning="收到 observation 后结束")

    with mock.patch.object(LeadAgent, "_decide_with_llm", patched_decide_with_llm):
        goal = "请帮我做一个完整的知识库播客工作流"
        result = await orchestrator.run(goal, on_event=on_event)
        assert result.route == "harness"

    # There should be 2 decide calls; second one should receive non-empty history
    assert len(captured_calls) == 2
    assert captured_calls[0].get("history") == [] or captured_calls[0].get("history") is None
    assert "tool_results" in captured_calls[0]
    assert len(captured_calls[1].get("history", [])) == 1
    assert "tool_results" in captured_calls[1]
    obs = captured_calls[1]["history"][0]
    assert obs.action_taken == "planningupdate"
    assert obs.success is True

import pytest
from backend.agent.capabilities import AgentCapabilities
from backend.harness.tools.providers import ListProvidersTool, ListProvidersInput


@pytest.mark.asyncio
async def test_list_providers_tool_returns_details():
    caps = AgentCapabilities()
    tool = ListProvidersTool(caps)
    result = await tool.run(ListProvidersInput(type="all", detailed=False))
    assert isinstance(result.llm_providers, list)
    assert isinstance(result.tts_providers, list)
    for p in result.llm_providers:
        assert p.id is not None
        assert p.name


@pytest.mark.asyncio
async def test_build_with_loop_uses_list_providers_tool(db, monkeypatch):
    monkeypatch.setattr("backend.config.settings.harness_loop_enabled", True)
    registry, _, _ = _registry()
    from backend.harness.schemas import CallToolDecision, FinalizeDecision
    from backend.harness.lead_agent import LeadAgent

    orchestrator = HarnessOrchestrator(db, registry=registry, lead_agent=LeadAgent(registry, db=db))
    with mock.patch.object(
        LeadAgent, "decide", side_effect=[
            CallToolDecision(name="list_providers", arguments={"type": "all", "detailed": False}),
            FinalizeDecision(reasoning="已获取提供商信息，提交"),
        ]
    ):
        context = await orchestrator.build("请帮我做一个完整的知识库播客工作流")
        events = context.events
        tool_calls = [e for e in events if e["type"] == "tool_call"]
        tool_results = [e for e in events if e["type"] == "tool_result"]
        assert len(tool_calls) == 1
        assert tool_calls[0]["name"] == "list_providers"
        assert len(tool_results) == 1
        assert tool_results[0]["ok"] is True
