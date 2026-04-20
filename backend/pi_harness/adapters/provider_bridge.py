from __future__ import annotations

from sqlalchemy.orm import Session

from backend.config import settings
from backend.models.provider import Provider
from backend.providers import build_provider


DEFAULT_LLM_MODEL_BY_TYPE: dict[str, str] = {
    "openai": "gpt-4o",
    "anthropic": "claude-3-5-sonnet-latest",
    "google": "gemini-2.0-flash",
    "deepseek": "deepseek-chat",
    "openai_compatible": "gpt-4o-mini",
}


def _resolve_default_model(
    provider_type: str,
    selected_models: list[str] | None = None,
) -> str:
    if selected_models:
        return selected_models[0]
    return DEFAULT_LLM_MODEL_BY_TYPE.get(provider_type, "gpt-4o")


class DBModelResolver:
    """Resolve a LangChain chat model from PIAgent's provider database."""

    def __init__(self, db: Session):
        self.db = db

    def get_model(
        self,
        provider_id: int | None = None,
        *,
        model_name: str | None = None,
        temperature: float = 0,
        streaming: bool = True,
        **kwargs,
    ):
        provider_row = self._resolve_provider(provider_id)
        provider = build_provider(provider_row)
        selected_model = model_name or settings.agent_llm_model or _resolve_default_model(
            provider_row.type,
            selected_models=provider_row.selected_models or [],
        )
        return provider.create_chat_model(
            model=selected_model,
            temperature=temperature,
            streaming=streaming,
            **kwargs,
        )

    def _resolve_provider(self, provider_id: int | None = None) -> Provider:
        effective_id = provider_id or settings.agent_llm_provider_id
        query = self.db.query(Provider).filter(
            Provider.enabled.is_(True),
            Provider.category == "llm",
        )
        if effective_id is not None:
            row = query.filter(Provider.id == effective_id).first()
        else:
            row = query.order_by(Provider.id.asc()).first()
        if row is None:
            raise RuntimeError("No enabled LLM provider is available for pi_harness")
        return row

