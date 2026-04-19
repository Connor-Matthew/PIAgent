from __future__ import annotations

import asyncio
from collections.abc import Awaitable, Callable
from dataclasses import dataclass, field
from typing import Any

from sqlalchemy.orm import Session

from backend.database import SessionLocal
from backend.models.provider import Provider
from backend.providers import build_provider
from backend.tts import build_tts_provider

EventCallback = Callable[[dict[str, Any]], Awaitable[None]]


@dataclass
class RunContext:
    db_factory: Callable[[], Session] = SessionLocal
    on_event: EventCallback | None = None
    cancel_event: asyncio.Event | None = None
    run_id: str | None = None
    owns_db_session: bool = True
    _llm_providers: dict[int, Any] = field(default_factory=dict)
    _tts_providers: dict[int, Any] = field(default_factory=dict)

    async def emit(self, event: dict[str, Any]) -> None:
        if self.on_event is not None:
            await self.on_event(event)

    def _load_provider_row(self, provider_id: int, expected_category: str | None = None) -> Provider:
        db = self.db_factory()
        try:
            row = db.query(Provider).filter(Provider.id == provider_id).first()
            if not row:
                raise ValueError(f"Provider not found: {provider_id}")
            if not row.enabled:
                raise ValueError(f"Provider is disabled: {provider_id}")
            if expected_category and row.category != expected_category:
                raise ValueError(
                    f"Provider {provider_id} has category {row.category}, expected {expected_category}"
                )
            return row
        finally:
            if self.owns_db_session:
                db.close()

    def get_llm_provider(self, provider_id: int) -> Any:
        if provider_id not in self._llm_providers:
            self._llm_providers[provider_id] = build_provider(
                self._load_provider_row(provider_id, expected_category="llm")
            )
        return self._llm_providers[provider_id]

    def get_tts_provider(self, provider_id: int) -> Any:
        if provider_id not in self._tts_providers:
            self._tts_providers[provider_id] = build_tts_provider(
                self._load_provider_row(provider_id, expected_category="tts")
            )
        return self._tts_providers[provider_id]
