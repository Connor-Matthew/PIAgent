from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field


class HarnessGraphDraft(BaseModel):
    model_config = ConfigDict(extra="forbid")

    nodes: list[dict] = Field(default_factory=list)
    edges: list[dict] = Field(default_factory=list)
    planning_notes: list[str] = Field(default_factory=list)
    committed: bool = False

    @property
    def graph(self) -> dict:
        return {
            "nodes": self.nodes,
            "edges": self.edges,
        }


class SkillInvocation(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: str = Field(min_length=1)
    arguments: dict[str, Any] = Field(default_factory=dict)


class SkillResult(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: str = Field(min_length=1)
    ok: bool = True
    value: Any = None
    error: str | None = None
    events: list[dict] = Field(default_factory=list)


class HarnessRunResult(BaseModel):
    model_config = ConfigDict(extra="forbid")

    goal: str
    route: Literal["fast", "harness"]
    graph: dict
    state: dict[str, Any] | None = None
    recipe: dict | None = None
    events: list[dict] = Field(default_factory=list)
    planning_notes: list[str] = Field(default_factory=list)
    defaults_applied: bool = False
    session_id: str | None = None


class SubAgentReport(BaseModel):
    model_config = ConfigDict(extra="forbid")

    agent_name: str
    observations: list[dict] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)


class GraphCriticReport(BaseModel):
    model_config = ConfigDict(extra="forbid")

    risks: list[dict] = Field(default_factory=list)
    score: int = Field(default=100, ge=0, le=100)


class CapabilityScoutReport(BaseModel):
    model_config = ConfigDict(extra="forbid")

    recommendations: list[dict] = Field(default_factory=list)
    reasoning: str = Field(default="")
    warnings: list[str] = Field(default_factory=list)


class RecipeChallengerReport(BaseModel):
    model_config = ConfigDict(extra="forbid")

    score: int = Field(default=100, ge=0, le=100)
    concerns: list[str] = Field(default_factory=list)
    alternatives: list[str] = Field(default_factory=list)
    reasoning: str = Field(default="")


class PlanStep(BaseModel):
    model_config = ConfigDict(extra="forbid")

    type: Literal["skill", "action", "finish"]
    name: str | None = None
    input: dict | None = None
    action: dict | None = None


class LeadAgentPlan(BaseModel):
    model_config = ConfigDict(extra="forbid")

    reasoning: str = Field(min_length=1)
    steps: list[PlanStep] = Field(default_factory=list)


class HarnessSessionRead(BaseModel):
    model_config = ConfigDict(extra="forbid")

    session_id: str
    goal: str
    route: Literal["fast", "harness"]
    status: str
    graph: dict | None = None
    recipe: dict | None = None
    events: list[dict] = Field(default_factory=list)


class LeadDecision(BaseModel):
    model_config = ConfigDict(extra="forbid")
    reasoning: str
    action: dict | None = None
    skill: str | None = None
    skill_input: dict | None = None
    done: bool = False


class DecisionObservation(BaseModel):
    model_config = ConfigDict(extra="forbid")
    step_index: int
    action_taken: str
    success: bool
    error: str | None = None
    graph_snapshot: dict | None = None
    skill_result_summary: str | None = None


class CallToolDecision(BaseModel):
    model_config = ConfigDict(extra="forbid")
    kind: Literal["call_tool"] = "call_tool"
    name: str = Field(min_length=1)
    arguments: dict[str, Any] = Field(default_factory=dict)


class SpawnSubAgentDecision(BaseModel):
    model_config = ConfigDict(extra="forbid")
    kind: Literal["spawn_subagent"] = "spawn_subagent"
    name: str = Field(min_length=1)
    brief: str = Field(min_length=1)


class ProposeActionDecision(BaseModel):
    model_config = ConfigDict(extra="forbid")
    kind: Literal["propose_action"] = "propose_action"
    action: dict = Field(min_length=1)


class AskUserDecision(BaseModel):
    model_config = ConfigDict(extra="forbid")
    kind: Literal["ask_user"] = "ask_user"
    question: str = Field(min_length=1)
    options: list[str] | None = None


class FinalizeDecision(BaseModel):
    model_config = ConfigDict(extra="forbid")
    kind: Literal["finalize"] = "finalize"
    reasoning: str = Field(default="")


DecisionV2 = (
    CallToolDecision
    | SpawnSubAgentDecision
    | ProposeActionDecision
    | AskUserDecision
    | FinalizeDecision
)


class LoopTraceEntry(BaseModel):
    model_config = ConfigDict(extra="forbid")

    step_index: int
    decision: DecisionV2
    observation: DecisionObservation
    timestamp: float


def decision_v2_to_lead_decision(decision: DecisionV2) -> LeadDecision:
    """Adapter: DecisionV2 -> old LeadDecision for boundary compatibility."""
    if isinstance(decision, CallToolDecision):
        return LeadDecision(
            reasoning=f"调用工具: {decision.name}",
            skill=decision.name,
            skill_input=decision.arguments,
        )
    if isinstance(decision, SpawnSubAgentDecision):
        return LeadDecision(
            reasoning=f"启动子 Agent: {decision.name}",
            skill="spawn_subagent",
            skill_input={"name": decision.name, "brief": decision.brief},
        )
    if isinstance(decision, ProposeActionDecision):
        return LeadDecision(
            reasoning="提出图操作",
            action=decision.action,
        )
    if isinstance(decision, AskUserDecision):
        return LeadDecision(
            reasoning=f"询问用户: {decision.question}",
            action={"kind": "planning_update", "text": f"需要澄清: {decision.question}"},
        )
    if isinstance(decision, FinalizeDecision):
        return LeadDecision(
            reasoning=decision.reasoning or " finalize graph",
            done=True,
        )
    raise ValueError(f"Unknown DecisionV2 type: {type(decision)}")
