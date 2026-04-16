import httpx

from backend.tts.base import BaseTTSProvider


class MiniMaxTTSProvider(BaseTTSProvider):
    name = "minimax_tts"

    def __init__(
        self,
        api_key: str,
        model: str = "speech-2.8-hd",
        base_url: str = "https://api.minimaxi.com",
    ):
        self.api_key = api_key
        self.model = model
        self.base_url = base_url.rstrip("/")

    def _build_payload(self, text: str, voice: str, **kwargs) -> dict:
        voice_setting = {
            "voice_id": voice,
            "speed": kwargs.get("speed", 1.0),
            "vol": 1,
            "pitch": 0,
            "emotion": kwargs.get("emotion", "happy"),
        }
        audio_setting = {
            "sample_rate": 32000,
            "bitrate": 128000,
            "format": "mp3",
            "channel": 1,
        }

        payload = {
            "model": self.model,
            "text": text,
            "stream": False,
            "voice_setting": voice_setting,
            "audio_setting": audio_setting,
        }
        return payload

    async def synthesize_bytes(
        self,
        text: str,
        voice: str = "male-qn-qingse",
        **kwargs,
    ) -> bytes:
        payload = self._build_payload(text=text, voice=voice, **kwargs)

        async with httpx.AsyncClient() as client:
            resp = await client.post(
                f"{self.base_url}/v1/t2a_v2",
                json=payload,
                headers={"Authorization": f"Bearer {self.api_key}"},
                timeout=60.0,
            )
            resp.raise_for_status()
            data = resp.json()

        base_resp = data.get("base_resp", {})
        if base_resp.get("status_code") != 0:
            raise RuntimeError(
                f"MiniMax TTS error: {base_resp.get('status_msg', 'unknown error')}"
            )

        audio_hex = data["data"]["audio"]
        return bytes.fromhex(audio_hex)

    def test_connection(self) -> None:
        """Send a minimal synthesis request to verify the key."""
        import asyncio

        async def _test():
            await self.synthesize_bytes(
                text="你好",
                voice="male-qn-qingse",
                emotion="neutral",
                speed=1,
            )

        asyncio.run(_test())
