from langchain_openai import OpenAIEmbeddings
from backend.config import settings


def get_embedding_model(provider: str = "openai"):
    if provider == "openai":
        api_key = settings.openai_api_key.get_secret_value() if settings.openai_api_key else None
        return OpenAIEmbeddings(api_key=api_key)
    raise ValueError(f"Unknown embedding provider: {provider}")
