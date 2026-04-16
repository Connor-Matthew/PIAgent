from backend.models.provider import Provider as ProviderModel
from backend.core.crypto import decrypt
from backend.providers.base import BaseLLMProvider
from backend.providers.anthropic_provider import AnthropicProvider
from backend.providers.deepseek_provider import DeepSeekProvider
from backend.providers.google_provider import GoogleProvider
from backend.providers.openai_provider import OpenAIProvider
from backend.providers.openai_compatible_provider import OpenAICompatibleProvider

PROVIDER_REGISTRY: dict[str, type[BaseLLMProvider]] = {
    "openai": OpenAIProvider,
    "anthropic": AnthropicProvider,
    "google": GoogleProvider,
    "deepseek": DeepSeekProvider,
    "openai_compatible": OpenAICompatibleProvider,
}


def build_provider(row: ProviderModel) -> BaseLLMProvider:
    cls = PROVIDER_REGISTRY[row.type]
    return cls(
        api_key=decrypt(row.api_key_encrypted),
        base_url=row.base_url,
        extra=row.extra_config or {},
    )
