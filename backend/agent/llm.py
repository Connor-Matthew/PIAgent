from typing import TypeVar

from langchain_core.messages import HumanMessage, SystemMessage
from pydantic import BaseModel
from sqlalchemy.orm import Session

from backend.agent.defaults import resolve_default_llm_model
from backend.config import settings
from backend.models.provider import Provider
from backend.providers import build_provider

SchemaModelT = TypeVar("SchemaModelT", bound=BaseModel)


class AgentLLMDisabledError(Exception):
    pass


class AgentLLMClient:
    def __init__(self, db: Session):
        self.db = db

    def structured_invoke(
        self,
        *,
        schema: type[SchemaModelT],
        system_prompt: str,
        user_prompt: str,
        provider_id: int | None = None,
    ) -> SchemaModelT:
        if not settings.agent_llm_enabled:
            raise AgentLLMDisabledError("AGENT_LLM_ENABLED is disabled")

        provider_row = self._resolve_provider(provider_id)
        provider = build_provider(provider_row)
        model_name = resolve_default_llm_model(
            provider_row.type,
            selected_models=provider_row.selected_models or [],
            cached_models=(provider_row.extra_config or {}).get("cached_models") or [],
        )
        chat_model = provider.create_chat_model(
            model=model_name,
            temperature=0,
            streaming=False,
        )
        if provider_row.type == "openai_compatible":
            structured_model = chat_model.with_structured_output(schema, method="json_mode")
        else:
            structured_model = chat_model.with_structured_output(schema)
        messages = [
            SystemMessage(content=system_prompt),
            HumanMessage(content=user_prompt),
        ]
        result = structured_model.invoke(messages)
        if isinstance(result, schema):
            return result
        if isinstance(result, dict):
            return schema.model_validate(result)
        return schema.model_validate(result.model_dump())

    def _resolve_provider(self, provider_id: int | None) -> Provider:
        query = self.db.query(Provider).filter(
            Provider.enabled.is_(True),
            Provider.category == "llm",
        )
        if provider_id is not None:
            provider_row = query.filter(Provider.id == provider_id).first()
        else:
            provider_row = query.order_by(Provider.id.asc()).first()
        if provider_row is None:
            raise RuntimeError("No enabled LLM provider is available for agent planning")
        return provider_row
