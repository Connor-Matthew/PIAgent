from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy.orm import Session

from backend.agent.defaults import resolve_default_llm_model, resolve_default_tts_voices
from backend.models.knowledge_base import KnowledgeBase
from backend.models.provider import Provider


class AgentCapabilityError(Exception):
    pass


class LLMProviderCapability(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: int
    type: str
    name: str
    default_model: str


class TTSProviderCapability(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: int
    type: str
    name: str
    voices: list[str] = Field(default_factory=list)


class KnowledgeBaseCapability(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: str
    name: str
    doc_count: int = 0


class AgentCapabilities(BaseModel):
    model_config = ConfigDict(extra="forbid")

    llm_providers: list[LLMProviderCapability] = Field(default_factory=list)
    tts_providers: list[TTSProviderCapability] = Field(default_factory=list)
    knowledge_bases: list[KnowledgeBaseCapability] = Field(default_factory=list)

    @property
    def has_llm_providers(self) -> bool:
        return bool(self.llm_providers)

    @property
    def has_tts_providers(self) -> bool:
        return bool(self.tts_providers)

    @property
    def has_knowledge_bases(self) -> bool:
        return bool(self.knowledge_bases)

    def get_llm_provider(self, provider_id: int | None) -> LLMProviderCapability | None:
        if provider_id is None:
            return None
        for provider in self.llm_providers:
            if provider.id == provider_id:
                return provider
        return None

    def get_tts_provider(self, provider_id: int | None) -> TTSProviderCapability | None:
        if provider_id is None:
            return None
        for provider in self.tts_providers:
            if provider.id == provider_id:
                return provider
        return None

    def get_knowledge_base(
        self, knowledge_base_id: str | None
    ) -> KnowledgeBaseCapability | None:
        if knowledge_base_id is None:
            return None
        for knowledge_base in self.knowledge_bases:
            if knowledge_base.id == knowledge_base_id:
                return knowledge_base
        return None

    def first_llm_provider(self) -> LLMProviderCapability | None:
        return self.llm_providers[0] if self.llm_providers else None

    def first_tts_provider(self) -> TTSProviderCapability | None:
        return self.tts_providers[0] if self.tts_providers else None

    def first_knowledge_base(self) -> KnowledgeBaseCapability | None:
        return self.knowledge_bases[0] if self.knowledge_bases else None

    def require_llm_provider(self) -> LLMProviderCapability:
        provider = self.first_llm_provider()
        if provider is None:
            raise AgentCapabilityError(
                "Agent mode requires at least one enabled LLM provider"
            )
        return provider


def load_capabilities(db: Session) -> AgentCapabilities:
    llm_rows = (
        db.query(Provider)
        .filter(Provider.enabled.is_(True), Provider.category == "llm")
        .order_by(Provider.id.asc())
        .all()
    )
    tts_rows = (
        db.query(Provider)
        .filter(Provider.enabled.is_(True), Provider.category == "tts")
        .order_by(Provider.id.asc())
        .all()
    )
    knowledge_base_rows = db.query(KnowledgeBase).order_by(KnowledgeBase.id.asc()).all()

    llm_providers = [
        LLMProviderCapability(
            id=row.id,
            type=row.type,
            name=row.name,
            default_model=resolve_default_llm_model(
                row.type,
                selected_models=row.selected_models or [],
                cached_models=(row.extra_config or {}).get("cached_models") or [],
            ),
        )
        for row in llm_rows
    ]
    tts_providers = [
        TTSProviderCapability(
            id=row.id,
            type=row.type,
            name=row.name,
            voices=resolve_default_tts_voices(row.type, row.extra_config or {}),
        )
        for row in tts_rows
    ]
    knowledge_bases = [
        KnowledgeBaseCapability(
            id=row.id,
            name=row.name,
            doc_count=row.doc_count or 0,
        )
        for row in knowledge_base_rows
    ]

    return AgentCapabilities(
        llm_providers=llm_providers,
        tts_providers=tts_providers,
        knowledge_bases=knowledge_bases,
    )
