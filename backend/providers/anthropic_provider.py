from langchain_anthropic import ChatAnthropic
from backend.providers.base import BaseLLMProvider
from backend.config import settings

class AnthropicProvider(BaseLLMProvider):
    name = "anthropic"

    def get_chat_model(self, model: str = "claude-sonnet-4-20250514", temperature: float = 0.7, streaming: bool = True):
        return ChatAnthropic(
            model=model,
            temperature=temperature,
            streaming=streaming,
            api_key=settings.anthropic_api_key.get_secret_value() if settings.anthropic_api_key else "",
        )

    def list_models(self) -> list[str]:
        return ["claude-sonnet-4-20250514", "claude-haiku-4-20250414"]

    async def test_connection(self) -> bool:
        try:
            model = self.get_chat_model(streaming=False)
            await model.ainvoke("hi")
            return True
        except Exception:
            return False
