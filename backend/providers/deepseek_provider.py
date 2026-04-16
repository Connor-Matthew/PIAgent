from backend.providers.openai_provider import OpenAIProvider


class DeepSeekProvider(OpenAIProvider):
    type = "deepseek"
    default_base_url = "https://api.deepseek.com"
