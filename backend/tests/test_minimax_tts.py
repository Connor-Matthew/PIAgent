import pytest
from unittest.mock import AsyncMock, patch, MagicMock

from backend.tts.minimax import MiniMaxTTSProvider


@pytest.mark.asyncio
async def test_minimax_synthesize_success(tmp_path):
    provider = MiniMaxTTSProvider(api_key="sk-test", model="speech-2.8-hd")

    mock_resp = MagicMock()
    mock_resp.raise_for_status = MagicMock()
    mock_resp.json.return_value = {
        "base_resp": {"status_code": 0, "status_msg": "success"},
        "data": {"audio": "00010203"},
    }

    with patch("httpx.AsyncClient.post", new_callable=AsyncMock) as mock_post:
        mock_post.return_value = mock_resp
        url = await provider.synthesize(
            text="你好",
            voice="male-qn-qingse",
            output_dir=str(tmp_path),
            emotion="happy",
            speed=1.2,
        )

    assert url.startswith("/audio/")
    assert url.endswith(".mp3")
    mock_post.assert_awaited_once()
    call_args = mock_post.await_args
    assert call_args.kwargs["json"]["model"] == "speech-2.8-hd"
    assert call_args.kwargs["json"]["voice_setting"]["emotion"] == "happy"
    assert call_args.kwargs["json"]["voice_setting"]["speed"] == 1.2


@pytest.mark.asyncio
async def test_minimax_synthesize_api_error(tmp_path):
    provider = MiniMaxTTSProvider(api_key="sk-test")

    mock_resp = MagicMock()
    mock_resp.raise_for_status = MagicMock()
    mock_resp.json.return_value = {
        "base_resp": {"status_code": 1001, "status_msg": "bad request"},
        "data": {},
    }

    with patch("httpx.AsyncClient.post", new_callable=AsyncMock) as mock_post:
        mock_post.return_value = mock_resp
        with pytest.raises(RuntimeError, match="MiniMax TTS error"):
            await provider.synthesize(text="你好", output_dir=str(tmp_path))


def test_minimax_test_connection_success():
    provider = MiniMaxTTSProvider(api_key="sk-test")

    mock_resp = MagicMock()
    mock_resp.raise_for_status = MagicMock()
    mock_resp.json.return_value = {
        "base_resp": {"status_code": 0, "status_msg": "success"},
        "data": {"audio": "0001"},
    }

    with patch("httpx.AsyncClient.post", new_callable=AsyncMock) as mock_post:
        mock_post.return_value = mock_resp
        provider.test_connection()

    mock_post.assert_awaited_once()
    call_args = mock_post.await_args
    assert call_args.kwargs["json"]["text"] == "你好"
