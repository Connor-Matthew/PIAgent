from backend.providers.openai_provider import OpenAIProvider


class OpenAICompatibleProvider(OpenAIProvider):
    type = "openai_compatible"
    default_base_url = None
