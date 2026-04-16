import logging
from langchain_core.language_models.chat_models import BaseChatModel
from langchain_google_genai import ChatGoogleGenerativeAI

from backend.providers.base import BaseLLMProvider, ProviderAuthError, ProviderError

logger = logging.getLogger(__name__)


class GoogleProvider(BaseLLMProvider):
    type = "google"
    default_base_url = None
    supports_list_models = False

    def list_models(self) -> list[str]:
        return [
            "gemini-2.0-flash",
            "gemini-2.0-pro",
            "gemini-1.5-flash",
            "gemini-1.5-pro",
        ]

    def test_connection(self) -> None:
        try:
            model = self.create_chat_model(model="gemini-2.0-flash", streaming=False)
            model.invoke("hi")
        except Exception as e:
            msg = str(e).lower()
            auth_indicators = (
                "api key not valid",
                "permission denied",
                "unauthorized",
                "authentication",
                "invalid api key",
            )
            if any(ind in msg for ind in auth_indicators):
                raise ProviderAuthError(f"Connection test failed: {e}") from e
            raise ProviderError(f"Connection test failed: {e}") from e

    def create_chat_model(self, model: str, **kwargs) -> BaseChatModel:
        return ChatGoogleGenerativeAI(
            model=model,
            google_api_key=self.api_key,
            **kwargs,
        )
