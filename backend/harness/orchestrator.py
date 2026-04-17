from __future__ import annotations

from sqlalchemy.orm import Session

from backend.agent.capabilities import AgentCapabilityError
from backend.agent.llm import AgentLLMClient
from backend.harness.actions import (
    AddEdgeAction,
    AddNodeAction,
    CommitGraphAction,
    PlanningUpdateAction,
    UpdateNodeConfigAction,
    coerce_graph_action,
)
from backend.harness.builder import GraphDraftBuilder
from backend.harness.context import HarnessContext, HarnessRoute
from backend.harness.lead_agent import LeadAgent, draft_to_actions
from backend.config import settings
from backend.harness.memory import HarnessMemoryStore, HarnessProjectMemoryStore
from backend.harness.registry import HarnessSkillRegistry
from backend.harness.schemas import HarnessRunResult
from backend.harness.subagents import (
    CapabilityScoutAgent,
    RecipeChallengerAgent,
)
from backend.harness.validators import GraphStructureValidator


FAST_ROUTE_KEYWORDS = (
    "fast",
    "quick",
    "simple",
    "lite",
    "简单",
    "快速",
    "轻量",
)

HARNESS_ROUTE_KEYWORDS = (
    "agent",
    "workflow",
    "orchestr",
    "plan",
    "multi-step",
    "复杂",
    "规划",
    "编排",
    "工作流",
    "画布",
    "节点",
    "知识库",
    "检索",
    "rag",
    "播客",
    "音频",
    "语音",
    "tts",
    "多轮",
    "构图",
    "执行",
)

MINIMAL_FAST_ROUTE_MAX_CHARS = 8


def _resolve_selected_llm(capabilities, recipe: dict | None, graph: dict | None) -> dict | None:
    provider_id = recipe.get("llm_provider_id") if isinstance(recipe, dict) else None
    model_name: str | None = None

    if isinstance(graph, dict):
        for node in graph.get("nodes", []):
            node_type = node.get("type")
            if node_type not in {"llm", "agent"}:
                continue
            data = node.get("data") or {}
            if provider_id is None:
                provider_id = data.get("provider_id")
            model_candidate = data.get("model")
            if isinstance(model_candidate, str) and model_candidate:
                model_name = model_candidate
                break

    provider = capabilities.get_llm_provider(provider_id) if provider_id is not None else None
    if provider is None:
        return None

    return {
        "id": provider.id,
        "name": provider.name,
        "type": provider.type,
        "model": model_name or provider.default_model,
    }


def _resolve_selected_tts(capabilities, recipe: dict | None) -> dict | None:
    if not isinstance(recipe, dict):
        return None

    provider_id = recipe.get("tts_provider_id")
    provider = capabilities.get_tts_provider(provider_id) if provider_id is not None else None
    if provider is None:
        return None

    return {
        "id": provider.id,
        "name": provider.name,
        "type": provider.type,
        "voice": recipe.get("tts_voice_id"),
    }


class HarnessOrchestrator:
    def __init__(
        self,
        db: Session,
        *,
        registry: HarnessSkillRegistry | None = None,
        lead_agent: LeadAgent | None = None,
        builder_cls=GraphDraftBuilder,
        memory_store: HarnessMemoryStore | None = None,
        project_memory_store: HarnessProjectMemoryStore | None = None,
        enable_subagents: bool = True,
    ):
        self.db = db
        self.registry = registry or HarnessSkillRegistry.from_db(db)
        self.lead_agent = lead_agent or LeadAgent(self.registry, db=self.db)
        self.builder_cls = builder_cls
        self.memory_store = memory_store or HarnessMemoryStore(db)
        self.project_memory_store = project_memory_store or HarnessProjectMemoryStore(db)
        self.enable_subagents = enable_subagents

    def select_route(self, goal: str) -> HarnessRoute:
        trimmed = goal.strip()
        normalized = trimmed.lower()

        if any(keyword in normalized for keyword in FAST_ROUTE_KEYWORDS if keyword.isascii()):
            return "fast"
        if any(keyword in trimmed for keyword in FAST_ROUTE_KEYWORDS if not keyword.isascii()):
            return "fast"

        if any(keyword in normalized for keyword in HARNESS_ROUTE_KEYWORDS if keyword.isascii()):
            return "harness"
        if any(keyword in trimmed for keyword in HARNESS_ROUTE_KEYWORDS if not keyword.isascii()):
            return "harness"

        if len(trimmed) <= MINIMAL_FAST_ROUTE_MAX_CHARS:
            return "fast"

        return "harness"

    async def build(self, goal: str, *, on_event=None, session_id: str | None = None) -> HarnessContext:
        route = self.select_route(goal)
        context = HarnessContext(goal=goal, route=route, session_id=session_id)

        async def emit(event: dict) -> None:
            context.events.append(event)
            if on_event is not None:
                await on_event(event)
            if session_id is not None:
                self.memory_store.append_event(session_id, event)

        # Initialize or resume session memory
        if session_id is None:
            record = self.memory_store.create_session(goal=goal, route=route)
            context.session_id = record.id
            session_id = record.id
        else:
            existing = self.memory_store.get_session(session_id)
            if existing is not None:
                context.memory = self.memory_store.build_snapshot(session_id)

        await emit({"type": "planning_start", "goal": goal, "route": context.route})

        # Load capabilities with skill events
        await emit({"type": "skill_start", "name": "load_capabilities"})
        try:
            capabilities = self.registry.capabilities.load()
            capabilities.require_llm_provider()
            context.capabilities = capabilities
            observe_event = self.registry.capabilities.observe(capabilities)
            await emit(observe_event)
            await emit({"type": "skill_end", "name": "load_capabilities", "ok": True})
        except AgentCapabilityError as exc:
            await emit({"type": "skill_end", "name": "load_capabilities", "ok": False, "error": str(exc)})
            await emit(
                {
                    "type": "planning_error",
                    "stage": "load_capabilities",
                    "message": str(exc),
                    "recoverable": False,
                }
            )
            raise

        # Load project memory preferences after capabilities are known
        project_prefs = self.project_memory_store.load("default")
        project_memory_summary = self.project_memory_store.apply_defaults(capabilities, project_prefs)
        if project_memory_summary:
            await emit({"type": "project_memory_loaded", "summary": project_memory_summary})

        if route == "harness" and settings.agent_llm_enabled and settings.harness_loop_enabled:
            return await self._build_with_loop(
                goal,
                route=route,
                context=context,
                emit=emit,
                capabilities=capabilities,
                project_memory_summary=project_memory_summary,
            )

        return await self._build_single_shot(
            goal,
            route=route,
            context=context,
            emit=emit,
            capabilities=capabilities,
            project_memory_summary=project_memory_summary,
        )

    async def _build_single_shot(self, goal, *, route, context, emit, capabilities, project_memory_summary):
        # Optional capability scout sub-agent
        if self.enable_subagents:
            await emit({"type": "subagent_spawned", "agent": CapabilityScoutAgent.name, "role": "capability_recommendation"})
            scout = CapabilityScoutAgent(llm=AgentLLMClient(self.db))
            scout_report = await scout.analyze({"goal": goal, "capabilities": capabilities})
            await emit({"type": "subagent_result", "agent": CapabilityScoutAgent.name, "report": scout_report.model_dump()})
            if scout_report.warnings:
                await emit({"type": "planning_update", "text": f"CapabilityScout 发现 {len(scout_report.warnings)} 条建议"})

        # Plan recipe with skill events
        await emit({"type": "skill_start", "name": "draft_recipe"})
        try:
            lead_plan = await self.lead_agent.plan(
                goal,
                route=context.route,
                capabilities=capabilities,
                project_memory_summary=project_memory_summary,
            )
            if lead_plan.draft is None:
                raise RuntimeError("LeadAgent failed to produce a workflow draft")
            context.recipe = lead_plan.draft.recipe_ir.model_dump()
            context.defaults_applied = lead_plan.draft.defaults_applied
            # Emit skill_end for each invocation recorded by LeadAgent
            for invocation in lead_plan.skill_invocations:
                if invocation.name == "draft_recipe":
                    await emit({"type": "skill_end", "name": invocation.name, "ok": invocation.ok, "error": invocation.error})
            await emit(
                {
                    "type": "planner_observe",
                    "name": "plan_recipe",
                    "summary": f"已选择 {lead_plan.draft.recipe_ir.recipe} 作为工作流骨架",
                    "recipe": context.recipe,
                }
            )

            builder = self.builder_cls(
                db=self.db,
                validation_skill=self.registry.graph_validation,
            )

            for action in lead_plan.actions:
                if isinstance(action, PlanningUpdateAction):
                    builder.apply(action)
                    await emit({"type": "planning_update", "text": action.text})
                    continue
                if isinstance(action, AddNodeAction):
                    builder.apply(action)
                    await emit({"type": "node_added", "node": action.node})
                    continue
                if isinstance(action, AddEdgeAction):
                    builder.apply(action)
                    await emit({"type": "edge_added", "edge": action.edge})
                    continue
                if isinstance(action, UpdateNodeConfigAction):
                    builder.apply(action)
                    await emit(
                        {
                            "type": "node_config_updated",
                            "node_id": action.node_id,
                            "patch": action.config,
                            "config": action.config,
                        }
                    )
                    continue
                if isinstance(action, CommitGraphAction):
                    # Optional sub-agent pre-commit checks
                    if self.enable_subagents:
                        await emit({"type": "subagent_spawned", "agent": RecipeChallengerAgent.name, "role": "recipe_review"})
                        challenger = RecipeChallengerAgent(llm=AgentLLMClient(self.db))
                        challenger_report = await challenger.analyze({"goal": goal, "recipe_ir": context.recipe})
                        await emit({"type": "subagent_result", "agent": RecipeChallengerAgent.name, "report": challenger_report.model_dump()})
                        if challenger_report.warnings:
                            await emit({"type": "planning_update", "text": f"RecipeChallenger 发现 {len(challenger_report.warnings)} 条建议"})

                        await emit({"type": "subagent_spawned", "agent": GraphStructureValidator.name, "role": "pre_commit_review"})
                        validator = GraphStructureValidator()
                        report = await validator.analyze({"graph": builder.graph})
                        await emit({"type": "subagent_result", "agent": GraphStructureValidator.name, "report": report.model_dump()})
                        if report.warnings:
                            await emit({"type": "planning_update", "text": f"GraphStructureValidator 发现 {len(report.warnings)} 条建议"})

                    draft = builder.apply(action)
                    context.draft = draft
                    graph = draft.graph
                    await emit(
                        {
                            "type": "workflow_built",
                            "graph": graph,
                            "node_count": len(graph.get("nodes", [])),
                            "edge_count": len(graph.get("edges", [])),
                        }
                    )
                    await emit(
                        {
                            "type": "plan_ready",
                            "graph": graph,
                            "recipe": context.recipe,
                            "defaults_applied": context.defaults_applied,
                            "selected_llm": _resolve_selected_llm(capabilities, context.recipe, graph),
                            "selected_tts": _resolve_selected_tts(capabilities, context.recipe),
                            "route": route,
                            "session_id": context.session_id,
                        }
                    )
                    continue

            # Learn from session for project memory
            self.project_memory_store.learn_from_session(context.session_id, context)

            # Persist final planning state to memory
            self.memory_store.finalize_session(
                context.session_id,
                graph=context.graph,
                recipe=context.recipe,
                events=list(context.events),
                status=f"harness_{route}_completed",
            )

            return context
        except Exception as exc:
            await emit({"type": "skill_end", "name": "draft_recipe", "ok": False, "error": str(exc)})
            await emit(
                {
                    "type": "planning_error",
                    "stage": "build",
                    "message": str(exc),
                    "recoverable": False,
                }
            )
            raise

    async def _build_with_loop(
        self,
        goal: str,
        *,
        route: HarnessRoute,
        context: HarnessContext,
        emit,
        capabilities,
        project_memory_summary,
    ) -> HarnessContext:
        from backend.harness.schemas import LeadDecision, DecisionObservation, LoopTraceEntry
        from backend.harness.prompts import build_lead_decision_system_prompt, build_lead_decision_user_prompt
        from backend.agent.llm import AgentLLMDisabledError
        import time

        builder = self.builder_cls(
            db=self.db,
            validation_skill=self.registry.graph_validation,
        )
        history: list[DecisionObservation] = []
        step = 0
        max_steps = settings.harness_loop_max_steps

        while step < max_steps:
            await emit({"type": "lead_step_start", "step": step})
            snapshot = builder.snapshot()

            try:
                decision = await self.lead_agent.decide(
                    goal,
                    route=route,
                    capabilities=capabilities,
                    project_memory_summary=project_memory_summary,
                    graph_snapshot=snapshot,
                    history=history,
                )
            except Exception:
                # Fall back to single-shot plan on any error
                await emit({"type": "lead_step_end", "step": step, "done": False, "fallback": True})
                return await self._build_single_shot(
                    goal,
                    route=route,
                    context=context,
                    emit=emit,
                    capabilities=capabilities,
                    project_memory_summary=project_memory_summary,
                )

            await emit({"type": "lead_decision", "step": step, "decision": decision.model_dump()})

            if decision.done:
                await emit({"type": "lead_step_end", "step": step, "done": True})
                break

            observation = await self._execute_decision(
                decision,
                builder,
                context,
                emit,
                goal,
                capabilities,
            )
            await emit({"type": "lead_observation", "step": step, "observation": observation.model_dump()})
            history.append(observation)
            context.loop_trace.append(
                LoopTraceEntry(
                    step_index=step,
                    decision=decision,
                    observation=observation,
                    timestamp=time.time(),
                )
            )
            await emit({"type": "lead_step_end", "step": step, "done": False})
            step += 1

        # Budget exceeded protection: force commit if not committed
        if step >= max_steps and not builder.draft.committed:
            await emit({"type": "planning_update", "text": "步数超限，强制提交当前图"})
            draft = builder.apply(CommitGraphAction())
            context.draft = draft
            graph = draft.graph
            await emit({"type": "workflow_built", "graph": graph, "node_count": len(graph.get("nodes", [])), "edge_count": len(graph.get("edges", []))})

        # If loop ended without building the final events, build them now
        if not builder.draft.committed:
            draft = builder.apply(CommitGraphAction())
            context.draft = draft
            graph = draft.graph
            await emit({"type": "workflow_built", "graph": graph, "node_count": len(graph.get("nodes", [])), "edge_count": len(graph.get("edges", []))})

        graph = builder.graph
        await emit({"type": "plan_ready", "graph": graph, "recipe": context.recipe, "defaults_applied": context.defaults_applied, "selected_llm": _resolve_selected_llm(capabilities, context.recipe, graph), "selected_tts": _resolve_selected_tts(capabilities, context.recipe), "route": route, "session_id": context.session_id})

        self.project_memory_store.learn_from_session(context.session_id, context)
        self.memory_store.finalize_session(context.session_id, graph=context.graph, recipe=context.recipe, events=list(context.events), status=f"harness_{route}_completed")
        return context

    async def _execute_decision(self, decision: "LeadDecision", builder: GraphDraftBuilder, context: HarnessContext, emit, goal: str, capabilities):
        from backend.harness.schemas import DecisionObservation
        from backend.agent.planner import PlannedDraft
        import time

        step_index = len(context.loop_trace)

        if decision.action:
            action = coerce_graph_action(decision.action)
            try:
                builder.apply(action)
                success = True
                error = None
                if isinstance(action, PlanningUpdateAction):
                    await emit({"type": "planning_update", "text": action.text})
                elif isinstance(action, AddNodeAction):
                    await emit({"type": "node_added", "node": action.node})
                elif isinstance(action, AddEdgeAction):
                    await emit({"type": "edge_added", "edge": action.edge})
                elif isinstance(action, UpdateNodeConfigAction):
                    await emit({"type": "node_config_updated", "node_id": action.node_id, "patch": action.config, "config": action.config})
                elif isinstance(action, CommitGraphAction):
                    # Optional sub-agent pre-commit checks (copy logic from existing build())
                    if self.enable_subagents:
                        await emit({"type": "subagent_spawned", "agent": RecipeChallengerAgent.name, "role": "recipe_review"})
                        challenger = RecipeChallengerAgent(llm=AgentLLMClient(self.db))
                        challenger_report = await challenger.analyze({"goal": goal, "recipe_ir": context.recipe})
                        await emit({"type": "subagent_result", "agent": RecipeChallengerAgent.name, "report": challenger_report.model_dump()})
                        if challenger_report.warnings:
                            await emit({"type": "planning_update", "text": f"RecipeChallenger 发现 {len(challenger_report.warnings)} 条建议"})

                        await emit({"type": "subagent_spawned", "agent": GraphStructureValidator.name, "role": "pre_commit_review"})
                        validator = GraphStructureValidator()
                        report = await validator.analyze({"graph": builder.graph})
                        await emit({"type": "subagent_result", "agent": GraphStructureValidator.name, "report": report.model_dump()})
                        if report.warnings:
                            await emit({"type": "planning_update", "text": f"GraphStructureValidator 发现 {len(report.warnings)} 条建议"})

                    context.draft = builder.draft
                    await emit({"type": "workflow_built", "graph": builder.graph, "node_count": len(builder.graph.get("nodes", [])), "edge_count": len(builder.graph.get("edges", []))})

                action_taken = action.__class__.__name__.replace("Action", "").lower()
            except Exception as exc:
                success = False
                error = str(exc)
                action_taken = decision.action.get("kind", "unknown")

            return DecisionObservation(
                step_index=step_index,
                action_taken=action_taken,
                success=success,
                error=error,
                graph_snapshot=builder.snapshot(),
            )

        if decision.skill:
            skill_name = decision.skill
            skill_input = decision.skill_input or {}
            try:
                if skill_name == "draft_recipe":
                    recipe_result = self.registry.recipe.invoke(goal=goal, **skill_input)
                    if recipe_result.ok:
                        draft = recipe_result.value
                        assert isinstance(draft, PlannedDraft)
                        context.recipe = draft.recipe_ir.model_dump()
                        context.defaults_applied = draft.defaults_applied
                        actions = draft_to_actions(draft, route=context.route)
                        for a in actions:
                            builder.apply(a)
                            if isinstance(a, PlanningUpdateAction):
                                await emit({"type": "planning_update", "text": a.text})
                            elif isinstance(a, AddNodeAction):
                                await emit({"type": "node_added", "node": a.node})
                            elif isinstance(a, AddEdgeAction):
                                await emit({"type": "edge_added", "edge": a.edge})
                            elif isinstance(a, CommitGraphAction):
                                context.draft = builder.draft
                                await emit({"type": "workflow_built", "graph": builder.graph, "node_count": len(builder.graph.get("nodes", [])), "edge_count": len(builder.graph.get("edges", []))})
                    skill_result_summary = f"draft_recipe ok={recipe_result.ok}"
                elif skill_name == "validate_graph":
                    self.registry.graph_validation.validate(builder.graph, db=self.db)
                    skill_result_summary = "validate_graph ok=True"
                elif skill_name == "load_capabilities":
                    skill_result_summary = "load_capabilities skipped"
                else:
                    skill_result_summary = f"unknown skill {skill_name}"
                success = True
                error = None
            except Exception as exc:
                success = False
                error = str(exc)
                skill_result_summary = str(exc)

            return DecisionObservation(
                step_index=step_index,
                action_taken=skill_name,
                success=success,
                error=error,
                graph_snapshot=builder.snapshot(),
                skill_result_summary=skill_result_summary,
            )

        # Neither action nor skill
        return DecisionObservation(
            step_index=step_index,
            action_taken="noop",
            success=True,
            graph_snapshot=builder.snapshot(),
        )

    async def run(
        self,
        goal: str,
        *,
        user_input: str | None = None,
        inputs: dict | None = None,
        on_event=None,
        session_id: str | None = None,
    ) -> HarnessRunResult:
        context = await self.build(goal, on_event=on_event, session_id=session_id)
        execution_inputs = inputs or {"input": user_input or goal}

        async def emit(event: dict) -> None:
            context.events.append(event)
            if on_event is not None:
                await on_event(event)
            if context.session_id is not None:
                self.memory_store.append_event(context.session_id, event)

        await emit({"type": "skill_start", "name": "run_graph"})
        state = await self.registry.execution.run(
            context.graph,
            user_input=user_input or goal,
            inputs=execution_inputs,
            on_event=emit,
        )
        await emit({"type": "skill_end", "name": "run_graph", "ok": True})
        context.state = state

        # Update memory with execution results
        if context.session_id is not None:
            self.memory_store.finalize_session(
                context.session_id,
                graph=context.graph,
                recipe=context.recipe,
                events=list(context.events),
                status=f"harness_{context.route}_completed",
            )

        return HarnessRunResult(
            goal=goal,
            route=context.route,
            graph=context.graph,
            state=state,
            recipe=context.recipe,
            events=list(context.events),
            planning_notes=list(context.draft.planning_notes),
            defaults_applied=context.defaults_applied,
            session_id=context.session_id,
        )
