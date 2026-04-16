import httpx
from langchain_core.language_models.chat_models import BaseChatModel
from langchain_openai import ChatOpenAI

from backend.providers.base import BaseLLMProvider, ProviderAuthError, ProviderError


class OpenAIProvider(BaseLLMProvider):
    type = "openai"
    default_base_url = "https://api.openai.com"

    def list_models(self) -> list[str]:
        url = f"{self.base_url.rstrip('/')}/v1/models"
        headers = {"Authorization": f"Bearer {self.api_key}"}
        try:
            resp = httpx.get(url, headers=headers, timeout=30)
            resp.raise_for_status()
            data = resp.json()
            models = [m["id"] for m in data.get("data", []) if m.get("id")]
            return sorted(set(models))
        except httpx.HTTPStatusError as e:
            if e.response.status_code in (401, 403):
                raise ProviderAuthError(f"Authentication failed: {e}") from e
            raise ProviderError(f"Failed to list models: {e}") from e
        except Exception as e:
            raise ProviderError(f"Failed to list models: {e}") from e

    def test_connection(self) -> None:
        try:
            self.list_models()
        except ProviderAuthError:
            raise
        except ProviderError:
            raise
        except Exception as e:
            raise ProviderError(f"Connection test failed: {e}") from e

    def create_chat_model(self, model: str, **kwargs) -> BaseChatModel:
        return ChatOpenAI(
            model=model,
            api_key=self.api_key,
            base_url=self.base_url,
            **kwargs,
        )
