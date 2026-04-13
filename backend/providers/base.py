from abc import ABC, abstractmethod
from typing import AsyncIterator
from langchain_core.messages import BaseMessage

class BaseLLMProvider(ABC):
    name: str = ""

    @abstractmethod
    def get_chat_model(self, model: str, temperature: float = 0.7, streaming: bool = True):
        """Return a LangChain ChatModel instance."""
        ...

    @abstractmethod
    def list_models(self) -> list[str]:
        """Return available model names."""
        ...

    @abstractmethod
    async def test_connection(self) -> bool:
        """Test if the provider API key is valid."""
        ...
