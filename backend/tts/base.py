from abc import ABC, abstractmethod


class BaseTTSProvider(ABC):
    name: str = ""

    @abstractmethod
    async def synthesize(self, text: str, voice: str = "default", output_dir: str = "./audio_files") -> str:
        """Synthesize text to audio. Returns the file path relative to audio serving."""
        ...
