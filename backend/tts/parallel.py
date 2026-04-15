import asyncio
from collections.abc import Awaitable, Callable
from typing import Any

from backend.tts.base import BaseTTSProvider
from backend.tts.chunker import split_text


async def with_retry(
    func: Callable[[], Awaitable[bytes]],
    *,
    retries: int = 2,
    base_delay: float = 0.5,
) -> bytes:
    for attempt in range(retries + 1):
        try:
            return await func()
        except Exception:
            if attempt == retries:
                raise
            await asyncio.sleep(base_delay * (2 ** attempt))
    raise RuntimeError("unreachable")


async def synthesize_long_text(
    provider: BaseTTSProvider,
    text: str,
    voice: str,
    output_dir: str,
    *,
    max_chars: int = 500,
    max_concurrency: int = 5,
    on_progress: Callable[[dict[str, Any]], Awaitable[None]] | None = None,
    **kwargs,
) -> str:
    chunks = split_text(text, max_chars=max_chars)
    if not chunks:
        return await provider.synthesize(text=text, voice=voice, output_dir=output_dir, **kwargs)
    if len(chunks) == 1:
        return await provider.synthesize(text=chunks[0], voice=voice, output_dir=output_dir, **kwargs)

    semaphore = asyncio.Semaphore(max_concurrency)
    total = len(chunks)
    done = 0
    done_lock = asyncio.Lock()

    async def _synthesize_chunk(chunk: str) -> bytes:
        nonlocal done
        async with semaphore:
            audio_bytes = await with_retry(
                lambda: provider.synthesize_bytes(text=chunk, voice=voice, **kwargs),
                retries=2,
            )
        async with done_lock:
            done += 1
            current = done
        if on_progress is not None:
            await on_progress({"current": current, "total": total})
        return audio_bytes

    results = await asyncio.gather(*[_synthesize_chunk(chunk) for chunk in chunks])
    return provider.write_audio_bytes(b"".join(results), output_dir=output_dir)
