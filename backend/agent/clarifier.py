import re

from sqlalchemy.orm import Session

from backend.agent.capabilities import AgentCapabilities
from backend.agent.llm import AgentLLMClient
from backend.agent.prompts import (
    build_clarifier_system_prompt,
    build_clarifier_user_prompt,
)
from backend.agent.planner import (
    AUDIO_KEYWORDS,
    NO_AUDIO_KEYWORDS,
    NO_KB_KEYWORDS,
)
from backend.agent.schemas import ClarificationTurn, ClarifyDecision


YES_TOKENS = ("是", "要", "需要", "可以", "yes", "y", "true", "行")
NO_TOKENS = ("否", "不", "不要", "不用", "no", "n", "false", "不需要")


class AgentClarifier:
    max_turns = 2

    def __init__(self, db: Session | None = None):
        self.db = db
        self.llm = AgentLLMClient(db) if db is not None else None

    def decide(
        self,
        *,
        goal: str,
        answered_dims: dict,
        turns: list[ClarificationTurn],
        capabilities: AgentCapabilities,
    ) -> ClarifyDecision:
        if len(turns) >= self.max_turns:
            return ClarifyDecision(
                need_more_info=False,
                rationale="Clarification reached the maximum turn limit",
            )

        if self.llm is not None and capabilities.has_llm_providers:
            try:
                return self._decide_with_llm(
                    goal=goal,
                    answered_dims=answered_dims,
                    turns=turns,
                    capabilities=capabilities,
                )
            except Exception:
                pass

        return self._decide_with_heuristic(
            goal=goal,
            answered_dims=answered_dims,
            turns=turns,
            capabilities=capabilities,
        )

    def _decide_with_heuristic(
        self,
        *,
        goal: str,
        answered_dims: dict,
        turns: list[ClarificationTurn],
        capabilities: AgentCapabilities,
    ) -> ClarifyDecision:
        lowered_goal = goal.lower()

        if (
            capabilities.has_tts_providers
            and "need_audio_output" not in answered_dims
            and not self._goal_explicitly_mentions_audio(lowered_goal)
        ):
            return ClarifyDecision(
                need_more_info=True,
                next_dim="need_audio_output",
                next_question="最终需要直接生成音频吗，还是只要脚本文本就可以？",
                rationale="是否生成音频会直接决定是否加入 tts 节点",
            )

        if (
            capabilities.has_knowledge_bases
            and "use_knowledge_base" not in answered_dims
            and not self._goal_explicitly_mentions_kb(lowered_goal)
        ):
            return ClarifyDecision(
                need_more_info=True,
                next_dim="use_knowledge_base",
                next_question="需要优先引用现有知识库资料来生成内容吗？",
                rationale="是否使用知识库会直接决定是否加入 rag 节点",
            )

        return ClarifyDecision(
            need_more_info=False,
            rationale="现有信息已足够生成当前 phase 的 workflow 草案",
        )

    def _decide_with_llm(
        self,
        *,
        goal: str,
        answered_dims: dict,
        turns: list[ClarificationTurn],
        capabilities: AgentCapabilities,
    ) -> ClarifyDecision:
        assert self.llm is not None
        lowered_goal = goal.lower()
        allowed_dims: list[str] = []
        if (
            capabilities.has_tts_providers
            and "need_audio_output" not in answered_dims
            and not self._goal_explicitly_mentions_audio(lowered_goal)
        ):
            allowed_dims.append("need_audio_output")
        if (
            capabilities.has_knowledge_bases
            and "use_knowledge_base" not in answered_dims
            and not self._goal_explicitly_mentions_kb(lowered_goal)
        ):
            allowed_dims.append("use_knowledge_base")
        filtered_dims = allowed_dims
        if not filtered_dims:
            return ClarifyDecision(
                need_more_info=False,
                rationale="All relevant clarification dimensions already have values",
            )

        return self.llm.structured_invoke(
            schema=ClarifyDecision,
            system_prompt=build_clarifier_system_prompt(self.max_turns),
            user_prompt=build_clarifier_user_prompt(
                goal=goal,
                answered_dims=answered_dims,
                turns=[turn.model_dump() for turn in turns],
                allowed_dims=filtered_dims,
                capabilities_summary={
                    "has_tts_providers": capabilities.has_tts_providers,
                    "has_knowledge_bases": capabilities.has_knowledge_bases,
                    "llm_provider_count": len(capabilities.llm_providers),
                },
            ),
        )

    def parse_answer(self, dim: str, answer: str) -> object | None:
        normalized = answer.strip().lower()
        if not normalized:
            return None

        if dim in {"need_audio_output", "use_knowledge_base", "include_code_snippets"}:
            return self._parse_bool(normalized)

        if dim == "duration_minutes":
            match = re.search(r"(\d+)", normalized)
            if not match:
                return None
            return max(1, min(int(match.group(1)), 120))

        if dim == "script_format":
            if any(token in normalized for token in ("对话", "双人", "dialogue", "访谈")):
                return "dialogue"
            if any(token in normalized for token in ("单口", "独白", "monologue")):
                return "monologue"
            return None

        if dim == "tone":
            if any(token in normalized for token in ("严肃", "technical", "技术")):
                return "serious_technical"
            if any(token in normalized for token in ("轻松", "casual", "科普")):
                return "casual_educational"
            if any(token in normalized for token in ("中性", "neutral")):
                return "neutral_explanatory"
            return None

        if dim == "audience_level":
            if any(token in normalized for token in ("本科", "undergraduate", "学生")):
                return "undergraduate_cs"
            if any(token in normalized for token in ("高级", "专家", "advanced")):
                return "advanced"
            if any(token in normalized for token in ("入门", "小白", "general")):
                return "general"
            if any(token in normalized for token in ("技术", "tech")):
                return "general_tech"
            return None

        return None

    def _goal_explicitly_mentions_audio(self, lowered_goal: str) -> bool:
        return any(token in lowered_goal for token in AUDIO_KEYWORDS) or any(
            token in lowered_goal for token in NO_AUDIO_KEYWORDS
        )

    def _goal_explicitly_mentions_kb(self, lowered_goal: str) -> bool:
        return any(token in lowered_goal for token in ("知识库", "检索", "rag")) or any(
            token in lowered_goal for token in NO_KB_KEYWORDS
        )

    def _parse_bool(self, normalized: str) -> bool | None:
        if any(token == normalized for token in ("y", "yes", "n", "no")):
            return normalized in {"y", "yes"}
        if any(token in normalized for token in NO_TOKENS):
            return False
        if any(token in normalized for token in YES_TOKENS):
            return True
        return None
