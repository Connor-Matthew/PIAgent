import json
from typing import Any

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from backend.assistant.agent import build_assistant_agent
from backend.assistant.session import append_turn, get_or_create_session, to_langchain_messages
from backend.database import get_db
from backend.models.workflow import Workflow

router = APIRouter(prefix="/api/assistant", tags=["assistant"])


class AssistantStreamRequest(BaseModel):
    message: str = Field(min_length=1)


def _sse(event: str, payload: dict[str, Any]) -> str:
    return f"event: {event}\ndata: {json.dumps(payload, ensure_ascii=False)}\n\n"


def _message_from_stream_item(item):
    if isinstance(item, tuple) and item:
        return item[0]
    return item


def _message_type(message) -> str:
    return str(getattr(message, "type", "") or message.__class__.__name__).lower()


def _message_content(message) -> str:
    content = getattr(message, "content", "")
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        return "".join(str(part) for part in content)
    return str(content or "")


@router.post("/sessions/{workflow_id}/stream")
async def stream_assistant(
    workflow_id: str,
    body: AssistantStreamRequest,
    db: Session = Depends(get_db),
):
    workflow = db.query(Workflow).filter(Workflow.id == workflow_id).first()
    if not workflow:
        raise HTTPException(status_code=404, detail="Workflow not found")

    session = get_or_create_session(db, workflow_id)
    messages = to_langchain_messages(session, body.message)
    agent = build_assistant_agent(db, workflow_id)

    async def event_generator():
        assistant_parts: list[str] = []
        yield _sse("session.started", {"workflow_id": workflow_id, "session_id": session.id})

        try:
            async for item in agent.astream({"messages": messages}, stream_mode="messages"):
                message = _message_from_stream_item(item)
                msg_type = _message_type(message)

                tool_calls = getattr(message, "tool_calls", None) or []
                for call in tool_calls:
                    yield _sse(
                        "tool.call",
                        {
                            "call_id": call.get("id"),
                            "tool": call.get("name"),
                            "args": call.get("args") or {},
                        },
                    )

                if msg_type == "tool":
                    content = _message_content(message)
                    summary = content if len(content) <= 500 else content[:500] + "..."
                    yield _sse(
                        "tool.result",
                        {
                            "call_id": getattr(message, "tool_call_id", None),
                            "tool": getattr(message, "name", None),
                            "summary": summary,
                        },
                    )
                    continue

                content = _message_content(message)
                if content:
                    assistant_parts.append(content)
                    yield _sse("message.delta", {"delta": content})

            assistant_text = "".join(assistant_parts)
            append_turn(db, session, body.message, assistant_text)
            yield _sse("message.done", {"content": assistant_text})
        except Exception as exc:
            yield _sse("error", {"message": str(exc)})

    return StreamingResponse(
        event_generator(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )
