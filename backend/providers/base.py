import logging
from abc import ABC, abstractmethod

from langchain_core.language_models.chat_models import BaseChatModel

logger = logging.getLogger(__name__)


class BaseLLMProvider(ABC):
    name: str = ""

    @abstractmethod
    def get_chat_model(
        self, model: str, temperature: float = 0.7, streaming: bool = True
    ) -> BaseChatModel:
        """Return a LangChain ChatModel instance."""
        ...

    @abstractmethod
    def list_models(self) -> list[str]:
        """Return available model names."""
        ...

    async def test_connection(self) -> bool:
        """Test if the provider API key is valid."""
        try:
            model = self.get_chat_model(streaming=False)
            await model.ainvoke("hi")
            return True
        except Exception:
            logger.exception("Provider connection test failed for %s", self.name)
            return False
