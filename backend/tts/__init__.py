from backend.models.provider import Provider as ProviderModel
from backend.core.crypto import decrypt
from backend.tts.base import BaseTTSProvider
from backend.tts.fish_audio import FishAudioProvider
from backend.tts.minimax import MiniMaxTTSProvider

TTS_PROVIDER_REGISTRY: dict[str, type[BaseTTSProvider]] = {
    "fish_audio": FishAudioProvider,
    "minimax_tts": MiniMaxTTSProvider,
}


def build_tts_provider(row: ProviderModel) -> BaseTTSProvider:
    cls = TTS_PROVIDER_REGISTRY[row.type]
    api_key = decrypt(row.api_key_encrypted)
    if row.type == "fish_audio":
        return cls(api_key=api_key, base_url=row.base_url)
    if row.type == "minimax_tts":
        return cls(api_key=api_key, base_url=row.base_url or "https://api.minimaxi.com")
    return cls(api_key=api_key)
