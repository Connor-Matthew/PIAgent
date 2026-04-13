from langchain_google_genai import ChatGoogleGenerativeAI
from backend.providers.base import BaseLLMProvider
from backend.config import settings

class GoogleProvider(BaseLLMProvider):
    name = "google"

    def get_chat_model(self, model: str = "gemini-2.0-flash", temperature: float = 0.7, streaming: bool = True):
        return ChatGoogleGenerativeAI(
            model=model,
            temperature=temperature,
            streaming=streaming,
            google_api_key=settings.google_api_key.get_secret_value() if settings.google_api_key else "",
        )

    def list_models(self) -> list[str]:
        return ["gemini-2.0-flash", "gemini-2.0-pro"]

    async def test_connection(self) -> bool:
        try:
            model = self.get_chat_model(streaming=False)
            await model.ainvoke("hi")
            return True
        except Exception:
            return False
