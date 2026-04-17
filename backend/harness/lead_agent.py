from __future__ import annotations

from dataclasses import dataclass, field
from typing import Literal

from sqlalchemy.orm import Session

from backend.agent.capabilities import AgentCapabilities
from backend.agent.llm import AgentLLMClient, AgentLLMDisabledError
from backend.agent.planner import PlannedDraft
from backend.config import settings
from backend.harness.actions import (
    AddEdgeAction,
    AddNodeAction,
    CommitGraphAction,
    GraphAction,
    PlanningUpdateAction,
    coerce_graph_action,
)
from backend.harness.context import HarnessRoute
from backend.harness.prompts import (
    build_lead_agent_system_prompt,
    build_lead_agent_user_prompt,
    build_lead_decision_v2_system_prompt,
    build_lead_decision_v2_user_prompt,
)
from backend.harness.registry import HarnessSkillRegistry
from backend.harness.schemas import LeadAgentPlan, LeadDecision, SkillResult, DecisionV2, decision_v2_to_lead_decision


@dataclass(slots=True)
class LeadPlan:
    goal: str
    route: HarnessRoute
    draft: PlannedDraft | None
    actions: list[GraphAction]
    skill_invocations: list[SkillResult] = field(default_factory=list)


class LeadAgent:
    def __init__(
        self,
        registry: HarnessSkillRegistry,
        db: Session,
        llm: AgentLLMClient | None = None,
    ):
        self.registry = registry
        self.db = db
        self.llm = llm or AgentLLMClient(db)

    async def plan(
        self,
        goal: str,
        *,
        route: HarnessRoute,
        capabilities: AgentCapabilities | None = None,
        project_memory_summary: dict | None = None,
    ) -> LeadPlan:
        if route == "fast" or not settings.agent_llm_enabled:
            return await self._plan_hardcoded(goal, route=route, capabilities=capabilities)
        try:
            return await self._plan_with_llm(
                goal,
                route=route,
                capabilities=capabilities,
                project_memory_summary=project_memory_summary,
            )
        except AgentLLMDisabledError:
            return await self._plan_hardcoded(goal, route=route, capabilities=capabilities)
        except Exception:
            return await self._plan_hardcoded(goal, route=route, capabilities=capabilities)

    async def _plan_hardcoded(
        self,
        goal: str,
        *,
        route: HarnessRoute,
        capabilities: AgentCapabilities | None = None,
    ) -> LeadPlan:
        skill_invocations: list[SkillResult] = []

        # Step 1: load capabilities
        capabilities_result = self.registry.capabilities.invoke()
        skill_invocations.append(capabilities_result)
        if not capabilities_result.ok:
            raise RuntimeError(
                f"Failed to load capabilities: {capabilities_result.error}"
            )
        loaded_capabilities = capabilities_result.value
        assert isinstance(loaded_capabilities, AgentCapabilities)
        loaded_capabilities.require_llm_provider()

        # Step 2: draft recipe
        recipe_result = self.registry.recipe.invoke(goal=goal)
        skill_invocations.append(recipe_result)
        if not recipe_result.ok:
            raise RuntimeError(f"Failed to draft recipe: {recipe_result.error}")
        draft = recipe_result.value
        assert isinstance(draft, PlannedDraft)

        actions = draft_to_actions(draft, route=route)
        return LeadPlan(
            goal=goal,
            route=route,
            draft=draft,
            actions=actions,
            skill_invocations=skill_invocations,
        )

    async def _plan_with_llm(
        self,
        goal: str,
        *,
        route: HarnessRoute,
        capabilities: AgentCapabilities | None = None,
        project_memory_summary: dict | None = None,
    ) -> LeadPlan:
        skill_invocations: list[SkillResult] = []
        actions: list[GraphAction] = []

        # Ensure capabilities are loaded for the prompt
        if capabilities is None:
            cap_result = self.registry.capabilities.invoke()
            skill_invocations.append(cap_result)
            if not cap_result.ok:
                raise RuntimeError(f"Failed to load capabilities: {cap_result.error}")
            capabilities = cap_result.value
            assert isinstance(capabilities, AgentCapabilities)
        capabilities.require_llm_provider()

        capabilities_summary = {
            "llm_providers": len(capabilities.llm_providers),
            "tts_providers": len(capabilities.tts_providers),
            "knowledge_bases": len(capabilities.knowledge_bases),
        }

        plan = self.llm.structured_invoke(
            schema=LeadAgentPlan,
            system_prompt=build_lead_agent_system_prompt(),
            user_prompt=build_lead_agent_user_prompt(
                goal=goal,
                route=route,
                capabilities_summary=capabilities_summary,
                memory_summary=project_memory_summary,
            ),
        )

        # Always emit the LLM reasoning as a planning update
        if plan.reasoning:
            actions.append(PlanningUpdateAction(text=plan.reasoning))

        draft: PlannedDraft | None = None
        has_commit_graph = False

        for step in plan.steps:
            if step.type == "finish":
                break
            if step.type == "action":
                if step.action:
                    action = coerce_graph_action(step.action)
                    actions.append(action)
                    if isinstance(action, CommitGraphAction):
                        has_commit_graph = True
                continue
            if step.type == "skill":
                name = step.name or ""
                if name == "load_capabilities":
                    # Already loaded above; record as no-op invocation
                    skill_invocations.append(
                        SkillResult(
                            name="load_capabilities",
                            ok=True,
                            value=capabilities,
                        )
                    )
                    continue
                if name == "draft_recipe":
                    recipe_result = self.registry.recipe.invoke(goal=goal)
                    skill_invocations.append(recipe_result)
                    if recipe_result.ok:
                        draft = recipe_result.value
                        assert isinstance(draft, PlannedDraft)
                    continue
                if name == "validate_graph":
                    # Deferred to builder/orchestrator at commit time
                    skill_invocations.append(
                        SkillResult(
                            name="validate_graph",
                            ok=True,
                            value={"deferred": True},
                        )
                    )
                    continue
                # Unknown skill: record failure but do not raise
                skill_invocations.append(
                    SkillResult(name=name, ok=False, error=f"Unknown skill: {name}")
                )
                continue

        # Append draft-derived actions if a draft was produced
        if draft is not None:
            actions.extend(draft_to_actions(draft, route=route))
            has_commit_graph = True
        elif not has_commit_graph:
            actions.append(CommitGraphAction())
            has_commit_graph = True

        return LeadPlan(
            goal=goal,
            route=route,
            draft=draft,
            actions=actions,
            skill_invocations=skill_invocations,
        )

    async def decide(
        self,
        goal: str,
        *,
        route: HarnessRoute,
        capabilities: AgentCapabilities | None = None,
        project_memory_summary: dict | None = None,
        graph_snapshot: dict | None = None,
        history: list | None = None,
        tool_results: list | None = None,
    ) -> DecisionV2:
        if route == "fast" or not settings.agent_llm_enabled:
            return await self._decide_hardcoded(
                goal,
                route=route,
                capabilities=capabilities,
                graph_snapshot=graph_snapshot,
            )
        return await self._decide_with_llm(
            goal,
            route=route,
            capabilities=capabilities,
            project_memory_summary=project_memory_summary,
            graph_snapshot=graph_snapshot,
            history=history,
            tool_results=tool_results,
        )

    async def _decide_hardcoded(
        self,
        goal: str,
        *,
        route: HarnessRoute,
        capabilities: AgentCapabilities | None = None,
        graph_snapshot: dict | None = None,
    ) -> DecisionV2:
        from backend.harness.schemas import FinalizeDecision
        committed = graph_snapshot.get("committed") if graph_snapshot else False
        if committed:
            return FinalizeDecision(reasoning="图已提交，循环结束")
        return FinalizeDecision(reasoning="硬编码路径：直接执行单次规划")

    async def _decide_with_llm(
        self,
        goal: str,
        *,
        route: HarnessRoute,
        capabilities: AgentCapabilities | None = None,
        project_memory_summary: dict | None = None,
        graph_snapshot: dict | None = None,
        history: list | None = None,
        tool_results: list | None = None,
    ) -> DecisionV2:
        from pydantic import TypeAdapter
        from backend.harness.schemas import DecisionV2

        if capabilities is None:
            cap_result = self.registry.capabilities.invoke()
            if not cap_result.ok:
                raise RuntimeError(f"Failed to load capabilities: {cap_result.error}")
            capabilities = cap_result.value
            assert isinstance(capabilities, AgentCapabilities)
        capabilities.require_llm_provider()

        raw = self.llm.structured_invoke(
            schema=dict,
            system_prompt=build_lead_decision_v2_system_prompt(),
            user_prompt=build_lead_decision_v2_user_prompt(
                goal=goal,
                route=route,
                memory_summary=project_memory_summary,
                graph_snapshot=graph_snapshot,
                history=history,
                tool_results=tool_results,
            ),
        )
        return TypeAdapter(DecisionV2).validate_python(raw)


def draft_to_actions(draft: PlannedDraft, *, route: HarnessRoute) -> list[GraphAction]:
    planning_text = draft.rationale_text or (
        "已生成最小可运行工作流草案"
        if route == "fast"
        else "已生成 harness 工作流草案"
    )
    actions: list[GraphAction] = [PlanningUpdateAction(text=planning_text)]

    for node in draft.graph.get("nodes", []):
        actions.append(AddNodeAction(node=node))

    for edge in draft.graph.get("edges", []):
        actions.append(AddEdgeAction(edge=edge))

    actions.append(CommitGraphAction())
    return actions
