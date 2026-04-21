"""PIAgent Harness v2 — API endpoints for /api/harness/*.

Replaces the old /api/agent/* and legacy harness endpoints.
Now powered by ReActBuilderAgentRunner (LangGraph create_react_agent).
"""

from __future__ import annotations

import asyncio
import contextlib
import json

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from backend.database import get_db
from backend.harness.react_session import (
    create_react_harness_session,
    load_react_harness_session,
)

# Backwards compatibility: old tests import _wire_session from this module.
# ReAct sessions do not need wiring, but we keep a no-op stub for test imports.
def _wire_session(hs):
    """No-op for backwards compatibility. ReAct sessions self-initialize."""
    pass

router = APIRouter(prefix="/api/harness", tags=["harness"])


# ── request/response schemas ──

class CreateSessionRequest(BaseModel):
    goal: str = Field(min_length=1)
    workflow_id: str | None = None


class CreateSessionResponse(BaseModel):
    session_id: str
    status: str


class ResumeRequest(BaseModel):
    question_id: str
    answer: str


class ContinueRequest(BaseModel):
    message: str = Field(min_length=1)


class ApplyResponse(BaseModel):
    workflow_id: str
    graph: dict


# ── endpoints ──

@router.post("/sessions", response_model=CreateSessionResponse)
async def create_session(
    body: CreateSessionRequest,
    db: Session = Depends(get_db),
):
    hs = create_react_harness_session(db, goal=body.goal, workflow_id=body.workflow_id)
    return CreateSessionResponse(session_id=hs.id, status=hs.status)


@router.get("/sessions/{session_id}")
async def get_session(session_id: str, db: Session = Depends(get_db)):
    hs = load_react_harness_session(session_id, db)
    return {
        "session_id": hs.id,
        "status": hs.status,
        "goal": hs.goal,
        "workflow_id": hs.workflow_id,
        "graph": hs.builder.snapshot(),
    }


@router.get("/sessions/{session_id}/events")
async def stream_events(
    session_id: str,
    request: Request,
    db: Session = Depends(get_db),
):
    hs = load_react_harness_session(session_id, db)

    async def event_generator():
        queue: asyncio.Queue[dict | None] = asyncio.Queue()
        terminal_event_sent = False

        async def emit(event: dict) -> None:
            nonlocal terminal_event_sent
            if event.get("type") == "session_end":
                terminal_event_sent = True
            await queue.put(event)
            await asyncio.sleep(0)

        async def produce() -> None:
            try:
                if hs.status == "awaiting_user":
                    # Already paused for a real ask_user question; don't re-run.
                    if hs.workspace.open_question:
                        open_question = hs.workspace.open_question
                        await emit({
                            "type": "awaiting_user_input",
                            "question_id": open_question.get("question_id"),
                            "prompt": open_question.get("question"),
                            "options": open_question.get("options"),
                        })
                    else:
                        await emit({"type": "session_end", "status": "awaiting_user"})
                elif hs.status == "waiting":
                    await emit({"type": "session_end", "status": "waiting"})
                elif hs.status == "running":
                    await hs.run(on_event=emit)
                elif hs.status == "ready":
                    await emit({"type": "harness_ready", "snapshot": hs.builder.snapshot()})
                elif hs.status == "applied":
                    await emit({"type": "session_end", "status": "applied"})
                else:
                    await emit({"type": "session_end", "status": hs.status})
            except Exception as exc:
                if not terminal_event_sent:
                    await emit({"type": "session_end", "status": "failed", "reason": str(exc)})
            finally:
                await queue.put(None)

        task = asyncio.create_task(produce())

        try:
            while True:
                if await request.is_disconnected():
                    if not task.done():
                        task.cancel()
                    break

                try:
                    event = await asyncio.wait_for(queue.get(), timeout=0.25)
                except asyncio.TimeoutError:
                    continue

                if event is None:
                    break
                yield (
                    f"event: {event['type']}\n"
                    f"data: {json.dumps(event, ensure_ascii=False)}\n\n"
                )
        finally:
            if not task.done():
                task.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await task

    return StreamingResponse(
        event_generator(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )


@router.post("/sessions/{session_id}/resume")
async def resume_session(
    session_id: str,
    body: ResumeRequest,
    db: Session = Depends(get_db),
):
    hs = load_react_harness_session(session_id, db)

    try:
        hs.queue_resume(body.question_id, body.answer)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    except RuntimeError as exc:
        raise HTTPException(status_code=409, detail=str(exc))

    return {"status": "resumed", "session_id": session_id}


@router.post("/sessions/{session_id}/messages")
async def continue_session(
    session_id: str,
    body: ContinueRequest,
    db: Session = Depends(get_db),
):
    hs = load_react_harness_session(session_id, db)

    try:
        hs.queue_user_message(body.message)
    except RuntimeError as exc:
        raise HTTPException(status_code=409, detail=str(exc))

    return {"status": "queued", "session_id": session_id}


@router.post("/sessions/{session_id}/apply")
async def apply_session(
    session_id: str,
    db: Session = Depends(get_db),
):
    hs = load_react_harness_session(session_id, db)
    result = await hs.apply()
    return ApplyResponse(**result)


@router.post("/sessions/{session_id}/abort")
async def abort_session(
    session_id: str,
    db: Session = Depends(get_db),
):
    hs = load_react_harness_session(session_id, db)
    hs.abort()
    return {"status": "aborted", "session_id": session_id}
