from langchain_openai import ChatOpenAI
from backend.providers.base import BaseLLMProvider
from backend.config import settings

class OpenAIProvider(BaseLLMProvider):
    name = "openai"

    def get_chat_model(self, model: str = "gpt-4o", temperature: float = 0.7, streaming: bool = True):
        return ChatOpenAI(
            model=model,
            temperature=temperature,
            streaming=streaming,
            api_key=settings.openai_api_key.get_secret_value() if settings.openai_api_key else "",
        )

    def list_models(self) -> list[str]:
        return ["gpt-4o", "gpt-4o-mini", "gpt-3.5-turbo"]

    async def test_connection(self) -> bool:
        try:
            model = self.get_chat_model(streaming=False)
            await model.ainvoke("hi")
            return True
        except Exception:
            return False
