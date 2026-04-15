import re


PRIMARY_DELIMITERS = "。！？!?\n"
SECONDARY_DELIMITERS = "，；,;"


def _split_with_delimiters(text: str, delimiters: str) -> list[str]:
    if not text:
        return []

    pattern = f"([{re.escape(delimiters)}])"
    parts = re.split(pattern, text)
    chunks: list[str] = []
    current = ""

    for part in parts:
        if not part:
            continue
        current += part
        if part in delimiters:
            chunks.append(current)
            current = ""

    if current:
        chunks.append(current)

    return [chunk for chunk in chunks if chunk]


def _force_split(text: str, max_chars: int) -> list[str]:
    return [text[i:i + max_chars] for i in range(0, len(text), max_chars)]


def split_text(text: str, max_chars: int = 500) -> list[str]:
    text = text.strip()
    if not text:
        return []
    if len(text) <= max_chars:
        return [text]

    first_pass = _split_with_delimiters(text, PRIMARY_DELIMITERS)
    second_pass: list[str] = []

    for part in first_pass:
        if len(part) <= max_chars:
            second_pass.append(part)
            continue
        second_pass.extend(_split_with_delimiters(part, SECONDARY_DELIMITERS))

    forced: list[str] = []
    for part in second_pass:
        if len(part) <= max_chars:
            forced.append(part)
            continue
        forced.extend(_force_split(part, max_chars))

    merged: list[str] = []
    buffer = ""
    for part in forced:
        if not buffer:
            buffer = part
            continue
        if len(buffer) + len(part) <= max_chars:
            buffer += part
            continue
        merged.append(buffer)
        buffer = part

    if buffer:
        merged.append(buffer)

    return [chunk for chunk in merged if chunk]
