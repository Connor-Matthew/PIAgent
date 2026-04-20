from __future__ import annotations

import json
from typing import Any

from langchain_core.messages import messages_from_dict, messages_to_dict


def dump_workspace_state(
    *,
    messages: list,
    graph: dict,
    open_question: dict[str, Any] | None,
    status: str,
) -> str:
    payload = {
        "messages": messages_to_dict(messages),
        "graph": graph,
        "open_question": open_question,
        "status": status,
    }
    return json.dumps(payload, ensure_ascii=False)


def load_workspace_state(raw: str | None) -> dict[str, Any]:
    if not raw:
        return {
            "messages": [],
            "graph": {"version": 2, "nodes": [], "edges": []},
            "open_question": None,
            "status": "running",
        }

    data = json.loads(raw)
    message_dicts = data.get("messages") or []
    return {
        "messages": messages_from_dict(message_dicts),
        "graph": data.get("graph") or {"version": 2, "nodes": [], "edges": []},
        "open_question": data.get("open_question"),
        "status": data.get("status", "running"),
    }

