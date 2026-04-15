from unittest.mock import AsyncMock, MagicMock

import pytest

from backend.tts.base import BaseTTSProvider
from backend.tts.chunker import split_text
from backend.tts.parallel import synthesize_long_text


class FakeTTSProvider(BaseTTSProvider):
    def __init__(self):
        self.write_audio_bytes = MagicMock(side_effect=self._write_audio_bytes)
        self.synthesize = AsyncMock(return_value="/audio/single.mp3")

    async def synthesize_bytes(self, text: str, voice: str = "default", **kwargs) -> bytes:
        return f"<{text}>".encode()

    def _write_audio_bytes(self, audio_bytes: bytes, output_dir: str = "./audio_files") -> str:
        return f"/audio/{len(audio_bytes)}.mp3"


def test_split_text_short_text_passthrough():
    assert split_text("你好世界", max_chars=10) == ["你好世界"]


def test_split_text_prefers_sentence_boundaries():
    chunks = split_text("第一句。第二句。第三句。", max_chars=5)
    assert chunks == ["第一句。", "第二句。", "第三句。"]


def test_split_text_falls_back_to_commas_then_force_split():
    text = "这是一段特别长但是没有句号，只有逗号，所以需要继续切分，最后如果还是太长就强切"
    chunks = split_text(text, max_chars=8)
    assert all(len(chunk) <= 8 for chunk in chunks)
    assert "".join(chunks) == text


def test_split_text_handles_empty_string():
    assert split_text("   ", max_chars=10) == []


@pytest.mark.asyncio
async def test_synthesize_long_text_bypasses_short_text():
    provider = FakeTTSProvider()

    url = await synthesize_long_text(
        provider=provider,
        text="短文本",
        voice="voice",
        output_dir="/tmp",
        max_chars=10,
    )

    assert url == "/audio/single.mp3"
    provider.synthesize.assert_awaited_once()


@pytest.mark.asyncio
async def test_synthesize_long_text_chunks_and_reports_progress():
    provider = FakeTTSProvider()
    progress_events = []

    async def on_progress(event):
        progress_events.append(event)

    url = await synthesize_long_text(
        provider=provider,
        text="第一句。第二句。第三句。",
        voice="voice",
        output_dir="/tmp",
        max_chars=5,
        on_progress=on_progress,
    )

    assert url.startswith("/audio/")
    assert progress_events == [
        {"current": 1, "total": 3},
        {"current": 2, "total": 3},
        {"current": 3, "total": 3},
    ]
