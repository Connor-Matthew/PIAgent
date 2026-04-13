from langchain_core.language_models.chat_models import BaseChatModel
from langchain_google_genai import ChatGoogleGenerativeAI

from backend.config import settings
from backend.providers.base import BaseLLMProvider


class GoogleProvider(BaseLLMProvider):
    name = "google"
    DEFAULT_MODEL = "gemini-2.0-flash"

    def get_chat_model(
        self,
        model: str = DEFAULT_MODEL,
        temperature: float = 0.7,
        streaming: bool = True,
    ) -> BaseChatModel:
        return ChatGoogleGenerativeAI(
            model=model,
            temperature=temperature,
            streaming=streaming,
            google_api_key=(key if (key := settings.google_api_key.get_secret_value()) else None),
        )

    def list_models(self) -> list[str]:
        return ["gemini-2.0-flash", "gemini-2.0-pro"]
