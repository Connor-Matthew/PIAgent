import re
from dataclasses import dataclass, field

from pydantic import ValidationError
from sqlalchemy.orm import Session

from backend.agent.adapter import AgentAdapterError, WorkflowGraphAdapter
from backend.agent.capabilities import AgentCapabilities, load_capabilities
from backend.agent.generator import AgentGenerator
from backend.agent.llm import AgentLLMClient, AgentLLMDisabledError
from backend.agent.prompts import (
    build_copywriter_system_prompt,
    build_copywriter_user_prompt,
)
from backend.agent.schemas import BespokeCopy, RecipeIR, RecipeLiteral
from backend.agent.validator import RecipeValidationError, ensure_valid_recipe_ir
from backend.core.compiler import CompilerError, CycleDetectedError


NO_AUDIO_KEYWORDS = ("不需要音频", "无需音频", "不要音频", "text only", "no audio")
AUDIO_KEYWORDS = ("播客", "podcast", "音频", "audio", "tts")
NO_KB_KEYWORDS = ("不要知识库", "不需要知识库", "不要检索", "无需检索")
CODE_KEYWORDS = ("代码", "code", "示例", "snippet")
DIALOGUE_KEYWORDS = ("对谈", "双人", "dialogue", "访谈")
SERIOUS_TONE_KEYWORDS = ("严肃", "技术向", "technical", "深入")
CASUAL_TONE_KEYWORDS = ("轻松", "casual", "科普")
ADVANCED_AUDIENCE_KEYWORDS = ("高级", "专家", "advanced", "expert")
UNDERGRAD_AUDIENCE_KEYWORDS = ("本科", "undergraduate", "学生", "大学")
GENERAL_AUDIENCE_KEYWORDS = ("入门", "小白", "general", "初学")


@dataclass
class PlanAttemptFailure:
    failure_type: str
    errors: list[str]


@dataclass
class PlannedDraft:
    recipe_ir: RecipeIR
    graph: dict
    capabilities: AgentCapabilities
    events: list[dict] = field(default_factory=list)
    defaults_applied: bool = False
    rationale_text: str | None = None


class AgentPlanningError(Exception):
    def __init__(
        self,
        *,
        stage: str,
        message: str,
        recoverable: bool,
        events: list[dict] | None = None,
    ):
        super().__init__(message)
        self.stage = stage
        self.message = message
        self.recoverable = recoverable
        self.events = events or []


class AgentPlanner:
    max_repair_attempts = 2

    def __init__(self, db: Session):
        self.db = db
        self.generator = AgentGenerator(db)
        self.llm = AgentLLMClient(db)

    def plan_default(self, goal: str) -> PlannedDraft:
        return self._plan(goal=goal, answered_dims={})

    def plan_with_answers(self, goal: str, answered_dims: dict) -> PlannedDraft:
        return self._plan(goal=goal, answered_dims=answered_dims)

    def _plan(self, *, goal: str, answered_dims: dict) -> PlannedDraft:
        capabilities = load_capabilities(self.db)
        capabilities.require_llm_provider()

        heuristic_recipe = self._build_default_recipe(
            goal,
            capabilities,
            answered_dims=answered_dims,
        )
        supported_recipes = self._supported_recipes(capabilities)
        events: list[dict] = [{"type": "recipe_generating", "attempt": 1}]

        candidate: RecipeIR | None = None
        try:
            candidate = self.generator.generate(
                goal=goal,
                answered_dims=answered_dims,
                supported_recipes=supported_recipes,
                capabilities=capabilities,
                heuristic_defaults=heuristic_recipe.model_dump(),
            )
            return self._finalize_draft(
                recipe_ir=candidate,
                capabilities=capabilities,
                goal=goal,
                events=events,
                defaults_applied=False,
            )
        except Exception as exc:
            failure = self._normalize_failure(exc)

        repair_events, repaired_draft, final_failure = self._attempt_repairs(
            goal=goal,
            answered_dims=answered_dims,
            supported_recipes=supported_recipes,
            capabilities=capabilities,
            heuristic_recipe=heuristic_recipe,
            initial_failure=failure,
            initial_recipe=candidate,
        )
        events.extend(repair_events)
        if repaired_draft is not None:
            repaired_draft.events = events + repaired_draft.events
            return repaired_draft

        if final_failure.failure_type == "llm_unavailable":
            fallback_message = "Agent LLM 未启用，已使用能力感知默认草案"
        else:
            fallback_message = "Recipe generation failed after retries, using the capability-aware default draft"
        fallback_events = [
            {
                "type": "recipe_fallback",
                "stage": "generate",
                "message": fallback_message,
                "recoverable": True,
                "failure_type": final_failure.failure_type,
                "errors": final_failure.errors,
            }
        ]
        events.extend(fallback_events)
        try:
            return self._finalize_draft(
                recipe_ir=heuristic_recipe,
                capabilities=capabilities,
                goal=goal,
                events=events,
                defaults_applied=True,
            )
        except Exception as exc:
            terminal_failure = self._normalize_failure(exc)
            events.append(
                {
                    "type": "agent_error",
                    "stage": "generate",
                    "message": "Unable to build the fallback draft for the current runtime",
                    "recoverable": False,
                    "failure_type": terminal_failure.failure_type,
                    "errors": terminal_failure.errors,
                }
            )
            raise AgentPlanningError(
                stage="generate",
                message="Unable to build a runnable workflow draft",
                recoverable=False,
                events=events,
            ) from exc

    def _attempt_repairs(
        self,
        *,
        goal: str,
        answered_dims: dict,
        supported_recipes: list[str],
        capabilities: AgentCapabilities,
        heuristic_recipe: RecipeIR,
        initial_failure: PlanAttemptFailure,
        initial_recipe: RecipeIR | None,
    ) -> tuple[list[dict], PlannedDraft | None, PlanAttemptFailure]:
        if not self._can_repair(initial_failure):
            return [], None, initial_failure

        failure = initial_failure
        previous_recipe = initial_recipe.model_dump() if initial_recipe else None
        events: list[dict] = []

        for attempt in range(1, self.max_repair_attempts + 1):
            events.append(
                {
                    "type": "recipe_repairing",
                    "attempt": attempt,
                    "errors": failure.errors,
                    "failure_type": failure.failure_type,
                }
            )
            try:
                repaired_recipe = self.generator.repair(
                    goal=goal,
                    answered_dims=answered_dims,
                    supported_recipes=supported_recipes,
                    capabilities=capabilities,
                    heuristic_defaults=heuristic_recipe.model_dump(),
                    attempt=attempt,
                    previous_recipe=previous_recipe,
                    errors=failure.errors,
                )
                draft = self._finalize_draft(
                    recipe_ir=repaired_recipe,
                    capabilities=capabilities,
                    goal=goal,
                    events=[],
                    defaults_applied=False,
                )
                return events, draft, failure
            except Exception as exc:
                failure = self._normalize_failure(exc)
                previous_recipe = (
                    repaired_recipe.model_dump()
                    if "repaired_recipe" in locals()
                    else previous_recipe
                )
                if not self._can_repair(failure):
                    break

        return events, None, failure

    def _build_graph(
        self,
        recipe_ir: RecipeIR,
        capabilities: AgentCapabilities,
        *,
        system_prompt_override: str | None = None,
    ) -> dict:
        ensure_valid_recipe_ir(recipe_ir, capabilities)
        return WorkflowGraphAdapter(capabilities).build_graph(
            recipe_ir,
            system_prompt_override=system_prompt_override,
        )

    def _finalize_draft(
        self,
        *,
        recipe_ir: RecipeIR,
        capabilities: AgentCapabilities,
        goal: str,
        events: list[dict],
        defaults_applied: bool,
    ) -> PlannedDraft:
        bespoke = self._generate_bespoke_copy(
            goal=goal,
            recipe_ir=recipe_ir,
            capabilities=capabilities,
        )
        graph = self._build_graph(
            recipe_ir,
            capabilities,
            system_prompt_override=bespoke.system_prompt if bespoke else None,
        )
        rationale = (
            bespoke.rationale
            if bespoke and bespoke.rationale.strip()
            else self._build_rationale(recipe_ir, defaults_applied=defaults_applied)
        )
        return PlannedDraft(
            recipe_ir=recipe_ir,
            graph=graph,
            capabilities=capabilities,
            events=events,
            defaults_applied=defaults_applied,
            rationale_text=rationale,
        )

    def _generate_bespoke_copy(
        self,
        *,
        goal: str,
        recipe_ir: RecipeIR,
        capabilities: AgentCapabilities,
    ) -> BespokeCopy | None:
        try:
            return self.llm.structured_invoke(
                schema=BespokeCopy,
                system_prompt=build_copywriter_system_prompt(),
                user_prompt=build_copywriter_user_prompt(
                    goal=goal,
                    recipe_ir=recipe_ir.model_dump(),
                    capabilities_summary={
                        "has_tts_providers": capabilities.has_tts_providers,
                        "has_knowledge_bases": capabilities.has_knowledge_bases,
                    },
                ),
            )
        except Exception:
            return None

    def _normalize_failure(self, exc: Exception) -> PlanAttemptFailure:
        if isinstance(exc, ValidationError):
            return PlanAttemptFailure(
                failure_type="schema_failure",
                errors=[
                    ".".join(str(part) for part in err["loc"]) + f": {err['msg']}"
                    for err in exc.errors()
                ],
            )
        if isinstance(exc, RecipeValidationError):
            failure_type = (
                "missing_capability_context"
                if self._is_capability_error(exc.errors)
                else "schema_failure"
            )
            return PlanAttemptFailure(failure_type=failure_type, errors=exc.errors)
        if isinstance(exc, AgentLLMDisabledError):
            return PlanAttemptFailure(
                failure_type="llm_unavailable",
                errors=[str(exc)],
            )
        if isinstance(exc, (AgentAdapterError, CompilerError, CycleDetectedError, ValueError)):
            return PlanAttemptFailure(
                failure_type="graph_compile_failure",
                errors=[str(exc)],
            )
        return PlanAttemptFailure(
            failure_type="generation_error",
            errors=[str(exc) or exc.__class__.__name__],
        )

    def _is_capability_error(self, errors: list[str]) -> bool:
        capability_markers = (
            "provider",
            "knowledge base",
            "voice",
            "available",
            "llm_provider_id",
            "tts_provider_id",
            "knowledge_base_id",
        )
        normalized = " ".join(errors).lower()
        return any(marker in normalized for marker in capability_markers)

    def _can_repair(self, failure: PlanAttemptFailure) -> bool:
        return failure.failure_type in {
            "schema_failure",
            "missing_capability_context",
            "graph_compile_failure",
        }

    def _build_rationale(self, recipe_ir: RecipeIR, *, defaults_applied: bool) -> str:
        fragments = [f"选择了 `{recipe_ir.recipe}` 这条最低风险链路。"]
        if "rag" in recipe_ir.recipe:
            fragments.append("草案会先从知识库取上下文，再生成脚本。")
        else:
            fragments.append("当前草案直接从用户目标生成脚本。")
        if "tts" in recipe_ir.recipe:
            fragments.append("草案会继续把脚本送入 TTS 节点生成音频。")
        else:
            fragments.append("当前草案只生成脚本文本，不直接合成音频。")
        if defaults_applied:
            fragments.append("这版使用了能力感知默认值，方便先落到一张可编辑的图。")
        return "".join(fragments)

    def _build_default_recipe(
        self,
        goal: str,
        capabilities: AgentCapabilities,
        answered_dims: dict,
    ) -> RecipeIR:
        normalized_goal = goal.strip()
        lowered_goal = normalized_goal.lower()

        desired_audio_output = answered_dims.get(
            "need_audio_output",
            self._detect_need_audio_output(lowered_goal),
        )
        desired_knowledge_base = answered_dims.get(
            "use_knowledge_base",
            self._detect_use_knowledge_base(lowered_goal, capabilities),
        )

        resolved_audio_output = desired_audio_output and capabilities.has_tts_providers
        resolved_knowledge_base = (
            desired_knowledge_base and capabilities.has_knowledge_bases
        )

        recipe = self._select_recipe(
            use_knowledge_base=resolved_knowledge_base,
            need_audio_output=resolved_audio_output,
        )

        llm_provider = capabilities.require_llm_provider()
        tts_provider = capabilities.first_tts_provider()
        knowledge_base = capabilities.first_knowledge_base()

        return RecipeIR(
            recipe=recipe,
            goal_summary=normalized_goal,
            audience_level=answered_dims.get(
                "audience_level",
                self._detect_audience(lowered_goal),
            ),
            tone=answered_dims.get("tone", self._detect_tone(lowered_goal)),
            duration_minutes=answered_dims.get(
                "duration_minutes",
                self._detect_duration_minutes(normalized_goal),
            ),
            script_format=answered_dims.get(
                "script_format",
                "dialogue"
                if any(keyword in lowered_goal for keyword in DIALOGUE_KEYWORDS)
                else "monologue",
            ),
            include_code_snippets=answered_dims.get(
                "include_code_snippets",
                any(keyword in lowered_goal for keyword in CODE_KEYWORDS),
            ),
            use_knowledge_base="rag" in recipe,
            need_audio_output="tts" in recipe,
            knowledge_base_id=knowledge_base.id if "rag" in recipe and knowledge_base else None,
            llm_provider_id=llm_provider.id,
            tts_provider_id=tts_provider.id if "tts" in recipe and tts_provider else None,
            tts_voice_id=(
                tts_provider.voices[0]
                if "tts" in recipe and tts_provider and tts_provider.voices
                else None
            ),
        )

    def _select_recipe(
        self,
        *,
        use_knowledge_base: bool,
        need_audio_output: bool,
    ) -> RecipeLiteral:
        if need_audio_output and use_knowledge_base:
            return "start_rag_llm_tts_end"
        if need_audio_output:
            return "start_llm_tts_end"
        if use_knowledge_base:
            return "start_rag_llm_end"
        return "start_llm_end"

    def _supported_recipes(self, capabilities: AgentCapabilities) -> list[str]:
        recipes = ["start_llm_end"]
        if capabilities.has_knowledge_bases:
            recipes.append("start_rag_llm_end")
        if capabilities.has_tts_providers:
            recipes.append("start_llm_tts_end")
        if capabilities.has_tts_providers and capabilities.has_knowledge_bases:
            recipes.append("start_rag_llm_tts_end")
        return recipes

    def _detect_need_audio_output(self, lowered_goal: str) -> bool:
        if any(keyword in lowered_goal for keyword in NO_AUDIO_KEYWORDS):
            return False
        if any(keyword in lowered_goal for keyword in AUDIO_KEYWORDS):
            return True
        return True

    def _detect_use_knowledge_base(
        self,
        lowered_goal: str,
        capabilities: AgentCapabilities,
    ) -> bool:
        if not capabilities.has_knowledge_bases:
            return False
        if any(keyword in lowered_goal for keyword in NO_KB_KEYWORDS):
            return False
        return True

    def _detect_audience(self, lowered_goal: str) -> str:
        if any(keyword in lowered_goal for keyword in ADVANCED_AUDIENCE_KEYWORDS):
            return "advanced"
        if any(keyword in lowered_goal for keyword in UNDERGRAD_AUDIENCE_KEYWORDS):
            return "undergraduate_cs"
        if any(keyword in lowered_goal for keyword in GENERAL_AUDIENCE_KEYWORDS):
            return "general"
        return "general_tech"

    def _detect_tone(self, lowered_goal: str) -> str:
        if any(keyword in lowered_goal for keyword in SERIOUS_TONE_KEYWORDS):
            return "serious_technical"
        if any(keyword in lowered_goal for keyword in CASUAL_TONE_KEYWORDS):
            return "casual_educational"
        return "casual_educational"

    def _detect_duration_minutes(self, goal: str) -> int:
        match = re.search(r"(\d+)\s*(分钟|min|mins|minutes)", goal, re.IGNORECASE)
        if not match:
            return 10
        try:
            value = int(match.group(1))
        except ValueError:
            return 10
        return max(1, min(value, 120))
