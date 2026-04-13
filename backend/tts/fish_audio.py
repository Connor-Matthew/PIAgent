import os
import uuid
import httpx

from backend.tts.base import BaseTTSProvider


class FishAudioProvider(BaseTTSProvider):
    name = "fish_audio"

    def __init__(self, api_key: str = "", base_url: str = "https://api.fish.audio"):
        self.api_key = api_key
        self.base_url = base_url

    async def synthesize(self, text: str, voice: str = "default", output_dir: str = "./audio_files") -> str:
        os.makedirs(output_dir, exist_ok=True)
        filename = f"{uuid.uuid4().hex}.mp3"
        filepath = os.path.join(output_dir, filename)

        # Fish Audio TTS API call
        async with httpx.AsyncClient() as client:
            resp = await client.post(
                f"{self.base_url}/v1/tts",
                json={"text": text, "reference_id": voice},
                headers={"Authorization": f"Bearer {self.api_key}"},
                timeout=60.0,
            )
            resp.raise_for_status()
            with open(filepath, "wb") as f:
                f.write(resp.content)

        return f"/audio/{filename}"
