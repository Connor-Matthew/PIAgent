import asyncio
import contextlib
import time
from abc import ABC, abstractmethod
from collections.abc import Awaitable, Callable
from typing import Any

from backend.core.state import WorkflowState

EventCallback = Callable[[dict[str, Any]], Awaitable[None]]


class BaseNode(ABC):
    node_type: str = ""

    def __init_subclass__(cls, **kwargs):
        super().__init_subclass__(**kwargs)
        if not cls.node_type:
            raise ValueError(f"{cls.__name__} must define a non-empty node_type")

    def __init__(self, config: dict[str, Any] | None = None):
        self.config = config or {}

    @property
    def node_id(self) -> str:
        return self.config.get("id", self.node_type)

    async def _emit(self, on_event: EventCallback | None, event: dict[str, Any]) -> None:
        if on_event is None:
            return
        await on_event(event)

    @staticmethod
    def _content_to_text(content: Any) -> str:
        if content is None:
            return ""
        if isinstance(content, str):
            return content
        if isinstance(content, list):
            return "".join(BaseNode._content_to_text(item) for item in content)
        if isinstance(content, dict):
            if isinstance(content.get("text"), str):
                return content["text"]
            if isinstance(content.get("content"), str):
                return content["content"]
        return str(content)

    @contextlib.asynccontextmanager
    async def heartbeat(
        self,
        on_event: EventCallback | None,
        *,
        message: str | Callable[[], str] | None = None,
        interval: float = 2.0,
    ):
        if on_event is None:
            yield
            return

        started_at = time.monotonic()

        async def _loop():
            while True:
                await asyncio.sleep(interval)
                payload = {
                    "type": "node_heartbeat",
                    "node_id": self.node_id,
                    "node_type": self.node_type,
                    "elapsed": round(time.monotonic() - started_at, 1),
                }
                heartbeat_message = message() if callable(message) else message
                if heartbeat_message:
                    payload["message"] = heartbeat_message
                await self._emit(on_event, payload)

        task = asyncio.create_task(_loop())
        try:
            yield
        finally:
            task.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await task

    @abstractmethod
    async def execute(self, state: WorkflowState, **kwargs) -> WorkflowState:
        ...
