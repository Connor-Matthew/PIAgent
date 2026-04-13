from langchain_core.language_models.chat_models import BaseChatModel
from langchain_openai import ChatOpenAI

from backend.config import settings
from backend.providers.base import BaseLLMProvider


class OpenAIProvider(BaseLLMProvider):
    name = "openai"
    DEFAULT_MODEL = "gpt-4o"

    def get_chat_model(
        self,
        model: str = DEFAULT_MODEL,
        temperature: float = 0.7,
        streaming: bool = True,
    ) -> BaseChatModel:
        return ChatOpenAI(
            model=model,
            temperature=temperature,
            streaming=streaming,
            api_key=(key if (key := settings.openai_api_key.get_secret_value()) else None),
        )

    def list_models(self) -> list[str]:
        return ["gpt-4o", "gpt-4o-mini", "gpt-3.5-turbo"]
