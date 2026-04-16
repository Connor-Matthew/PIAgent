import logging
from abc import ABC, abstractmethod
from typing import ClassVar

from langchain_core.language_models.chat_models import BaseChatModel

logger = logging.getLogger(__name__)


class ProviderError(Exception):
    pass


class ProviderAuthError(ProviderError):
    pass


class BaseLLMProvider(ABC):
    type: ClassVar[str] = ""
    default_base_url: ClassVar[str | None] = None
    supports_list_models: ClassVar[bool] = True

    def __init__(self, api_key: str, base_url: str | None = None, extra: dict | None = None):
        self.api_key = api_key
        self.base_url = base_url or self.default_base_url
        self.extra = extra or {}

    @abstractmethod
    def list_models(self) -> list[str]:
        """Return available model names."""
        ...

    @abstractmethod
    def test_connection(self) -> None:
        """Raise ProviderAuthError or ProviderError on failure."""
        ...

    @abstractmethod
    def create_chat_model(self, model: str, **kwargs) -> BaseChatModel:
        """Return a LangChain ChatModel instance."""
        ...
