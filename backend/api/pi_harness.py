from __future__ import annotations

import asyncio
import contextlib
import json

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from backend.database import get_db
from backend.pi_harness.session import (
    create_harness_session,
    load_harness_session,
)


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


def create_router(
    *,
    prefix: str = "/api/pi_harness",
    tags: list[str] | None = None,
) -> APIRouter:
    router = APIRouter(prefix=prefix, tags=tags or ["pi_harness"])

    @router.post("/sessions", response_model=CreateSessionResponse)
    async def create_session(
        body: CreateSessionRequest,
        db: Session = Depends(get_db),
    ):
        session = create_harness_session(
            db,
            goal=body.goal,
            workflow_id=body.workflow_id,
        )
        return CreateSessionResponse(session_id=session.id, status=session.status)

    @router.get("/sessions/{session_id}")
    async def get_session(session_id: str, db: Session = Depends(get_db)):
        session = load_harness_session(session_id, db)
        row = session._load_db()
        return {
            "session_id": session.id,
            "status": session.status,
            "goal": session.goal,
            "workflow_id": session.workflow_id,
            "graph": session.draft.snapshot(),
            "open_question": session.open_question,
            "events": [] if row is None else row.events,
        }

    @router.get("/sessions/{session_id}/events")
    async def stream_events(
        session_id: str,
        request: Request,
        db: Session = Depends(get_db),
    ):
        session = load_harness_session(session_id, db)

        async def event_generator():
            queue: asyncio.Queue[dict | None] = asyncio.Queue()
            terminal_event_sent = False

            async def emit(event: dict[str, object]) -> None:
                nonlocal terminal_event_sent
                if event.get("type") == "session_end":
                    terminal_event_sent = True
                await queue.put(event)
                await asyncio.sleep(0)

            async def produce() -> None:
                try:
                    if session.status == "awaiting_user":
                        await emit(
                            {
                                "type": "awaiting_user_input",
                                **(session.open_question or {}),
                            }
                        )
                    elif session.status == "running":
                        await session.run(on_event=emit)
                    elif session.status == "ready":
                        await emit(
                            {
                                "type": "harness_ready",
                                "snapshot": session.draft.snapshot(),
                            }
                        )
                        await emit({"type": "session_end", "status": "ready"})
                    elif session.status == "applied":
                        await emit({"type": "session_end", "status": "applied"})
                    else:
                        await emit({"type": "session_end", "status": session.status})
                except Exception as exc:
                    if not terminal_event_sent:
                        await emit(
                            {
                                "type": "session_end",
                                "status": "failed",
                                "reason": str(exc),
                            }
                        )
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
        session = load_harness_session(session_id, db)
        try:
            await session.record_user_answer(body.question_id, body.answer)
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc))
        except RuntimeError as exc:
            raise HTTPException(status_code=409, detail=str(exc))

        return {"status": "resumed", "session_id": session_id}

    @router.post("/sessions/{session_id}/apply", response_model=ApplyResponse)
    async def apply_session(
        session_id: str,
        db: Session = Depends(get_db),
    ):
        session = load_harness_session(session_id, db)
        result = await session.apply()
        return ApplyResponse(**result)

    @router.post("/sessions/{session_id}/abort")
    async def abort_session(
        session_id: str,
        db: Session = Depends(get_db),
    ):
        session = load_harness_session(session_id, db)
        session.abort()
        return {"status": "aborted", "session_id": session_id}

    return router


router = create_router()
