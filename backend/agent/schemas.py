from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator


ClarifyDim = Literal[
    "audience_level",
    "tone",
    "duration_minutes",
    "script_format",
    "include_code_snippets",
    "use_knowledge_base",
    "need_audio_output",
]

RecipeLiteral = Literal[
    "start_llm_end",
    "start_rag_llm_end",
    "start_llm_tts_end",
    "start_rag_llm_tts_end",
]

AudienceLevelLiteral = Literal[
    "general",
    "general_tech",
    "undergraduate_cs",
    "advanced",
]

ToneLiteral = Literal[
    "neutral_explanatory",
    "casual_educational",
    "serious_technical",
]

ScriptFormatLiteral = Literal["monologue", "dialogue"]


class ClarificationTurn(BaseModel):
    model_config = ConfigDict(extra="forbid")

    turn_index: int
    dim: ClarifyDim
    question: str
    user_answer: str | None = None


class ClarifyDecision(BaseModel):
    model_config = ConfigDict(extra="forbid")

    need_more_info: bool
    next_dim: ClarifyDim | None = None
    next_question: str | None = None
    rationale: str

    @model_validator(mode="after")
    def validate_follow_up_fields(self):
        if self.need_more_info:
            if not self.next_dim:
                raise ValueError("next_dim is required when need_more_info=true")
            if not self.next_question or not self.next_question.strip():
                raise ValueError("next_question is required when need_more_info=true")
        return self


class RecipeIR(BaseModel):
    model_config = ConfigDict(extra="forbid")

    recipe: RecipeLiteral
    goal_summary: str = Field(min_length=1)
    audience_level: AudienceLevelLiteral
    tone: ToneLiteral
    duration_minutes: int = Field(ge=1, le=120)
    script_format: ScriptFormatLiteral
    include_code_snippets: bool
    use_knowledge_base: bool
    need_audio_output: bool
    knowledge_base_id: str | None = None
    llm_provider_id: int | None = None
    tts_provider_id: int | None = None
    tts_voice_id: str | None = None

    @model_validator(mode="after")
    def validate_recipe_shape(self):
        recipe_has_rag = "rag" in self.recipe
        recipe_has_tts = "tts" in self.recipe

        if recipe_has_rag != self.use_knowledge_base:
            raise ValueError("use_knowledge_base must match the selected recipe")
        if recipe_has_tts != self.need_audio_output:
            raise ValueError("need_audio_output must match the selected recipe")
        if not self.use_knowledge_base and self.knowledge_base_id is not None:
            raise ValueError(
                "knowledge_base_id must be null when use_knowledge_base=false"
            )
        if not self.need_audio_output and (
            self.tts_provider_id is not None or self.tts_voice_id is not None
        ):
            raise ValueError(
                "tts_provider_id and tts_voice_id must be null when need_audio_output=false"
            )
        return self


class BespokeCopy(BaseModel):
    model_config = ConfigDict(extra="forbid")

    system_prompt: str = Field(min_length=1)
    rationale: str = Field(min_length=1)


class AgentSessionRead(BaseModel):
    model_config = ConfigDict(extra="forbid")

    session_id: str
    user_goal: str
    status: str
    clarification_turns: list[ClarificationTurn] = Field(default_factory=list)
    answered_dims: dict = Field(default_factory=dict)
    recipe_ir: RecipeIR | None = None
    generated_graph: dict | None = None
    rationale_text: str | None = None
    workflow_id: str | None = None
