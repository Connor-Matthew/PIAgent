from langchain_openai import ChatOpenAI
from backend.providers.base import BaseLLMProvider
from backend.config import settings

class DeepSeekProvider(BaseLLMProvider):
    name = "deepseek"

    def get_chat_model(self, model: str = "deepseek-chat", temperature: float = 0.7, streaming: bool = True):
        return ChatOpenAI(
            model=model,
            temperature=temperature,
            streaming=streaming,
            api_key=settings.deepseek_api_key.get_secret_value() if settings.deepseek_api_key else "",
            base_url="https://api.deepseek.com/v1",
        )

    def list_models(self) -> list[str]:
        return ["deepseek-chat", "deepseek-reasoner"]

    async def test_connection(self) -> bool:
        try:
            model = self.get_chat_model(streaming=False)
            await model.ainvoke("hi")
            return True
        except Exception:
            return False
