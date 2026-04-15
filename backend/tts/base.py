import os
import uuid
from abc import ABC, abstractmethod


class BaseTTSProvider(ABC):
    name: str = ""

    @abstractmethod
    async def synthesize_bytes(self, text: str, voice: str = "default", **kwargs) -> bytes:
        """Synthesize text and return raw audio bytes."""
        ...

    def write_audio_bytes(self, audio_bytes: bytes, output_dir: str = "./audio_files") -> str:
        os.makedirs(output_dir, exist_ok=True)
        filename = f"{uuid.uuid4().hex}.mp3"
        filepath = os.path.join(output_dir, filename)
        with open(filepath, "wb") as f:
            f.write(audio_bytes)
        return f"/audio/{filename}"

    async def synthesize(self, text: str, voice: str = "default", output_dir: str = "./audio_files", **kwargs) -> str:
        """Synthesize text to audio. Returns the file path relative to audio serving."""
        audio_bytes = await self.synthesize_bytes(text=text, voice=voice, **kwargs)
        return self.write_audio_bytes(audio_bytes, output_dir=output_dir)

    def test_connection(self) -> None:
        """Verify the provider credentials. Should raise on failure."""
        raise NotImplementedError("test_connection is not implemented for this provider")
