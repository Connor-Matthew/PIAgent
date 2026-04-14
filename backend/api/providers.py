from fastapi import APIRouter
from backend.providers.openai_provider import OpenAIProvider
from backend.providers.anthropic_provider import AnthropicProvider
from backend.providers.google_provider import GoogleProvider
from backend.providers.deepseek_provider import DeepSeekProvider

router = APIRouter(prefix="/api/providers", tags=["providers"])

ALL_PROVIDERS = {
    "openai": OpenAIProvider(),
    "anthropic": AnthropicProvider(),
    "google": GoogleProvider(),
    "deepseek": DeepSeekProvider(),
}

@router.get("")
def list_providers():
    return [{"name": p.name, "models": p.list_models()} for p in ALL_PROVIDERS.values()]

@router.get("/{provider_name}/models")
def get_models(provider_name: str):
    provider = ALL_PROVIDERS.get(provider_name)
    if not provider:
        return {"error": f"Unknown provider: {provider_name}"}
    return {"provider": provider_name, "models": provider.list_models()}

@router.post("/{provider_name}/test")
async def test_provider(provider_name: str):
    provider = ALL_PROVIDERS.get(provider_name)
    if not provider:
        return {"success": False, "error": f"Unknown provider: {provider_name}"}
    success = await provider.test_connection()
    return {"success": success, "provider": provider_name}
