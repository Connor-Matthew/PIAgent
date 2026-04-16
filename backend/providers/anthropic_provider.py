import httpx
from langchain_anthropic import ChatAnthropic
from langchain_core.language_models.chat_models import BaseChatModel

from backend.providers.base import BaseLLMProvider, ProviderAuthError, ProviderError


class AnthropicProvider(BaseLLMProvider):
    type = "anthropic"
    default_base_url = "https://api.anthropic.com"
    supports_list_models = True

    def list_models(self) -> list[str]:
        url = f"{self.base_url.rstrip('/')}/v1/models"
        headers = {
            "x-api-key": self.api_key,
            "anthropic-version": "2023-06-01",
        }
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
        except httpx.RequestError as e:
            # Network/transport errors: fallback to static list for list_models,
            # but re-raise as ProviderError so test_connection doesn't falsely pass.
            raise ProviderError(f"Network error listing models: {e}") from e

    def test_connection(self) -> None:
        try:
            models = self.list_models()
            if not models:
                raise ProviderAuthError("No models available")
        except ProviderAuthError:
            raise
        except ProviderError:
            raise
        except Exception as e:
            raise ProviderError(f"Connection test failed: {e}") from e

    def create_chat_model(self, model: str, **kwargs) -> BaseChatModel:
        return ChatAnthropic(
            model=model,
            api_key=self.api_key,
            **kwargs,
        )
