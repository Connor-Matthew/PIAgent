from langchain_core.language_models.chat_models import BaseChatModel
from langchain_openai import ChatOpenAI

from backend.config import settings
from backend.providers.base import BaseLLMProvider


class DeepSeekProvider(BaseLLMProvider):
    name = "deepseek"
    DEFAULT_MODEL = "deepseek-chat"

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
            api_key=(key if (key := settings.deepseek_api_key.get_secret_value()) else None),
            base_url="https://api.deepseek.com/v1",
        )

    def list_models(self) -> list[str]:
        return ["deepseek-chat", "deepseek-reasoner"]
