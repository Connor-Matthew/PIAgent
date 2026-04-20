from __future__ import annotations

import json


def parse_clarification_payload(content: str | list | None) -> dict | None:
    if not isinstance(content, str):
        return None

    try:
        data = json.loads(content)
    except (TypeError, json.JSONDecodeError):
        return None

    if isinstance(data, dict) and data.get("__clarification__"):
        return data
    return None


def summarize_tool_output(content: str | list | None, limit: int = 500) -> str:
    if isinstance(content, list):
        content = "\n".join(str(item) for item in content)
    text = "" if content is None else str(content)
    if len(text) <= limit:
        return text
    return text[:limit] + "..."

