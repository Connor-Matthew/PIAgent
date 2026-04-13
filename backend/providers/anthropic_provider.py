from langchain_anthropic import ChatAnthropic
from langchain_core.language_models.chat_models import BaseChatModel

from backend.config import settings
from backend.providers.base import BaseLLMProvider


class AnthropicProvider(BaseLLMProvider):
    name = "anthropic"
    DEFAULT_MODEL = "claude-sonnet-4-20250514"

    def get_chat_model(
        self,
        model: str = DEFAULT_MODEL,
        temperature: float = 0.7,
        streaming: bool = True,
    ) -> BaseChatModel:
        return ChatAnthropic(
            model=model,
            temperature=temperature,
            streaming=streaming,
            api_key=(key if (key := settings.anthropic_api_key.get_secret_value()) else None),
        )

    def list_models(self) -> list[str]:
        return ["claude-sonnet-4-20250514", "claude-haiku-4-20250414"]
