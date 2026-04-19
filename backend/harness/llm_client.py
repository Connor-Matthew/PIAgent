"""PIAgent Harness v2 — Lightweight LLM client for structured output.

Reuses the project's provider build logic but is self-contained
(no imports from backend.agent or backend.harness_legacy).
"""

from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor, TimeoutError as FuturesTimeoutError
from typing import Any, TypeVar, cast

from langchain_core.messages import HumanMessage, SystemMessage
from pydantic import BaseModel, TypeAdapter
from sqlalchemy.orm import Session

from backend.config import settings
from backend.models.provider import Provider
from backend.providers import build_provider

StructuredSchemaT = TypeVar("StructuredSchemaT")


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


class HarnessLLMClient:
    """Thin wrapper around the project's provider system for agent-style structured output."""

    def __init__(self, db: Session):
        self.db = db

    def structured_invoke(
        self,
        *,
        schema: Any,
        system_prompt: str,
        user_prompt: str,
        provider_id: int | None = None,
    ) -> StructuredSchemaT:
        provider_row = self._resolve_provider(provider_id)
        provider = build_provider(provider_row)
        model_name = settings.agent_llm_model or _resolve_default_model(
            provider_row.type,
            selected_models=provider_row.selected_models or [],
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

        timeout_seconds = settings.agent_llm_timeout_seconds
        executor = ThreadPoolExecutor(max_workers=1)
        future = executor.submit(structured_model.invoke, messages)
        try:
            result = future.result(timeout=timeout_seconds)
        except FuturesTimeoutError as exc:
            future.cancel()
            raise TimeoutError(f"Harness LLM timed out after {timeout_seconds:.1f}s") from exc
        finally:
            executor.shutdown(wait=False, cancel_futures=True)

        if isinstance(schema, type) and issubclass(schema, BaseModel) and isinstance(result, schema):
            return cast(StructuredSchemaT, result)

        adapter = TypeAdapter(schema)
        payload = result.model_dump() if isinstance(result, BaseModel) else result
        return cast(StructuredSchemaT, adapter.validate_python(payload))

    def _resolve_provider(self, provider_id: int | None) -> Provider:
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
            raise RuntimeError("No enabled LLM provider is available for harness")
        return row
