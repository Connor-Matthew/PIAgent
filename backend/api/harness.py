"""PIAgent Harness v2 — API endpoints for /api/harness/*.

Replaces the old /api/agent/* and legacy harness endpoints.
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
from backend.harness.session import (
    HarnessSession,
    create_harness_session,
    load_harness_session,
)
from backend.harness.tools import (
    HarnessContext,
    ListKnowledgeBasesTool,
    ListNodeTypesTool,
    ListProvidersTool,
    ListSkillsTool,
    PeekKnowledgeBaseTool,
    RecallPreferenceTool,
    ToolRegistry,
    ValidateGraphTool,
)

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


class ApplyResponse(BaseModel):
    workflow_id: str
    graph: dict


# ── helper: build a fully-wired HarnessSession ──

def _wire_session(hs: HarnessSession) -> HarnessSession:
    """Register default tools and init the lead agent."""
    hs.setup_tools(
        ListNodeTypesTool(),
        ListProvidersTool(),
        ListKnowledgeBasesTool(),
        PeekKnowledgeBaseTool(),
        ListSkillsTool(),
        RecallPreferenceTool(),
        ValidateGraphTool(),
    )
    hs.init_lead_agent()
    return hs


# ── endpoints ──

@router.post("/sessions", response_model=CreateSessionResponse)
async def create_session(
    body: CreateSessionRequest,
    db: Session = Depends(get_db),
):
    hs = create_harness_session(db, goal=body.goal, workflow_id=body.workflow_id)
    _wire_session(hs)
    return CreateSessionResponse(session_id=hs.id, status=hs.status)


@router.get("/sessions/{session_id}")
async def get_session(session_id: str, db: Session = Depends(get_db)):
    hs = load_harness_session(session_id, db)
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
    hs = load_harness_session(session_id, db)
    _wire_session(hs)

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
                    # Already paused; don't re-run, just wait (frontend will call resume)
                    await emit({"type": "awaiting_user_input", **hs.workspace.open_question})
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
    hs = load_harness_session(session_id, db)
    _wire_session(hs)

    try:
        await hs.record_user_answer(body.question_id, body.answer)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    except RuntimeError as exc:
        raise HTTPException(status_code=409, detail=str(exc))

    return {"status": "resumed", "session_id": session_id}


@router.post("/sessions/{session_id}/apply")
async def apply_session(
    session_id: str,
    db: Session = Depends(get_db),
):
    hs = load_harness_session(session_id, db)
    _wire_session(hs)
    result = await hs.apply()
    return ApplyResponse(**result)


@router.post("/sessions/{session_id}/abort")
async def abort_session(
    session_id: str,
    db: Session = Depends(get_db),
):
    hs = load_harness_session(session_id, db)
    hs.abort()
    return {"status": "aborted", "session_id": session_id}
