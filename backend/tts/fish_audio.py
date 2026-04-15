import httpx

from backend.tts.base import BaseTTSProvider
from backend.config import settings


class FishAudioProvider(BaseTTSProvider):
    name = "fish_audio"

    def __init__(self, api_key: str | None = None, base_url: str = "https://api.fish.audio"):
        self.api_key = api_key or (settings.fish_audio_api_key.get_secret_value() if settings.fish_audio_api_key else "")
        self.base_url = base_url

    async def synthesize_bytes(self, text: str, voice: str = "default", **kwargs) -> bytes:
        # Fish Audio TTS API call
        async with httpx.AsyncClient() as client:
            resp = await client.post(
                f"{self.base_url}/v1/tts",
                json={"text": text, "reference_id": voice},
                headers={"Authorization": f"Bearer {self.api_key}"},
                timeout=60.0,
            )
            resp.raise_for_status()
            return resp.content

    def test_connection(self) -> None:
        """Send a minimal synthesis request to verify the key."""
        import asyncio

        async def _test():
            async with httpx.AsyncClient() as client:
                resp = await client.post(
                    f"{self.base_url}/v1/tts",
                    json={"text": "hi", "reference_id": "default"},
                    headers={"Authorization": f"Bearer {self.api_key}"},
                    timeout=30.0,
                )
                resp.raise_for_status()

        asyncio.run(_test())
