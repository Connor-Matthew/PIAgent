import asyncio
import json

from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from backend.agent.capabilities import AgentCapabilityError, load_capabilities
from backend.agent.clarifier import AgentClarifier
from backend.agent.planner import AgentPlanner, AgentPlanningError, PlannedDraft
from backend.agent.schemas import ClarificationTurn
from backend.agent.session_store import AgentSessionStore
from backend.core.compiler import CompilerError, CycleDetectedError, GraphCompiler
from backend.database import get_db
from backend.models.workflow import Workflow

router = APIRouter(prefix="/api/agent", tags=["agent"])


class AgentSessionCreate(BaseModel):
    goal: str = Field(min_length=1)


class AgentSessionAnswer(BaseModel):
    answer: str = Field(min_length=1)


def _workflow_name_from_goal(goal: str) -> str:
    trimmed = goal.strip()
    if len(trimmed) <= 48:
        return trimmed
    return f"{trimmed[:45]}..."


def _build_question_event(turn: ClarificationTurn) -> dict:
    return {
        "type": "clarify_question",
        "turn_index": turn.turn_index,
        "next_dim": turn.dim,
        "question": turn.question,
    }


def _build_ready_event(record_id: str, draft: PlannedDraft) -> dict:
    payload = {
        "type": "plan_ready",
        "recipe": draft.recipe_ir.model_dump(),
        "graph": draft.graph,
        "defaults_applied": draft.defaults_applied,
        "session_id": record_id,
    }
    if draft.rationale_text:
        payload["rationale"] = draft.rationale_text
    return payload


def _finalize_session_to_ready(
    *,
    store: AgentSessionStore,
    record,
    draft: PlannedDraft,
) -> None:
    record.status = "ready"
    record.recipe = draft.recipe_ir.model_dump()
    record.graph = draft.graph
    record.rationale_text = draft.rationale_text
    completed_event = {
        "type": "clarify_completed",
        "total_turns": len(record.turns),
        "answered_dims": record.answered_dims,
    }
    events = list(record.events)
    events.append(completed_event)
    events.extend(draft.events)
    events.append(_build_ready_event(record.id, draft))
    record.events = events
    store.save(record)


def _finalize_session_to_failed(
    *,
    store: AgentSessionStore,
    record,
    error: AgentPlanningError,
) -> None:
    record.status = "failed"
    record.events = list(record.events) + error.events
    store.save(record)


def _count_consecutive_unresolved_turns(
    turns: list[ClarificationTurn],
    clarifier: AgentClarifier,
) -> int:
    unresolved = 0
    for turn in reversed(turns):
        if turn.user_answer is None:
            break
        parsed = clarifier.parse_answer(turn.dim, turn.user_answer)
        if parsed is not None:
            break
        unresolved += 1
    return unresolved


@router.post("/sessions", status_code=201)
def create_agent_session(
    body: AgentSessionCreate,
    db: Session = Depends(get_db),
):
    planner = AgentPlanner(db)
    store = AgentSessionStore(db)
    clarifier = AgentClarifier(db)
    try:
        capabilities = load_capabilities(db)
        capabilities.require_llm_provider()
    except AgentCapabilityError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    initial_event = {"type": "agent_session_started", "goal": body.goal}
    decision = clarifier.decide(
        goal=body.goal,
        answered_dims={},
        turns=[],
        capabilities=capabilities,
    )

    if decision.need_more_info:
        first_turn = ClarificationTurn(
            turn_index=1,
            dim=decision.next_dim,
            question=decision.next_question,
        )
        record = store.create(
            user_goal=body.goal,
            status="clarifying",
            clarification_turns=[first_turn],
            answered_dims={},
            events=[initial_event, _build_question_event(first_turn)],
        )
        events = list(record.events)
        events[0]["session_id"] = record.id
        record.events = events
        store.save(record)
        return {"session_id": record.id}

    record = store.create(
        user_goal=body.goal,
        status="generating",
        clarification_turns=[],
        answered_dims={},
        events=[initial_event],
    )
    events = list(record.events)
    events[0]["session_id"] = record.id
    record.events = events
    store.save(record)
    try:
        draft = planner.plan_default(body.goal)
    except AgentPlanningError as exc:
        _finalize_session_to_failed(store=store, record=record, error=exc)
        return {"session_id": record.id}

    _finalize_session_to_ready(store=store, record=record, draft=draft)
    return {"session_id": record.id}


@router.get("/sessions/{session_id}")
def get_agent_session(
    session_id: str,
    db: Session = Depends(get_db),
):
    store = AgentSessionStore(db)
    record = store.get_or_404(session_id)
    return store.to_read_model(record).model_dump()


@router.post("/sessions/{session_id}/answer", status_code=202)
def answer_agent_session(
    session_id: str,
    body: AgentSessionAnswer,
    db: Session = Depends(get_db),
):
    store = AgentSessionStore(db)
    planner = AgentPlanner(db)
    clarifier = AgentClarifier(db)
    record = store.get_or_404(session_id)

    if record.status != "clarifying":
        raise HTTPException(status_code=400, detail="Agent session is not waiting for an answer")

    turns = [ClarificationTurn.model_validate(turn) for turn in record.turns]
    if not turns:
        raise HTTPException(status_code=400, detail="Agent session has no pending question")
    current_turn = turns[-1]
    if current_turn.user_answer is not None:
        raise HTTPException(status_code=400, detail="Current question has already been answered")

    current_turn.user_answer = body.answer
    turns[-1] = current_turn
    record.turns = [turn.model_dump() for turn in turns]

    answered_dims = dict(record.answered_dims)
    parsed_value = clarifier.parse_answer(current_turn.dim, body.answer)
    if parsed_value is not None:
        answered_dims[current_turn.dim] = parsed_value
    record.answered_dims = answered_dims

    consecutive_unresolved = _count_consecutive_unresolved_turns(turns, clarifier)
    if consecutive_unresolved >= 2:
        record.status = "generating"
        record.events = list(record.events) + [
            {
                "type": "agent_error",
                "stage": "clarify",
                "message": "Clarification deadlock detected, switching to the default draft path",
                "recoverable": True,
                "failure_type": "clarification_deadlock",
                "errors": ["Two consecutive clarification turns produced no new structured dimension"],
            }
        ]
        store.save(record)
        try:
            draft = planner.plan_with_answers(record.user_goal, answered_dims)
        except AgentPlanningError as exc:
            _finalize_session_to_failed(store=store, record=record, error=exc)
            return {"status": "accepted"}
        _finalize_session_to_ready(store=store, record=record, draft=draft)
        return {"status": "accepted"}

    decision = clarifier.decide(
        goal=record.user_goal,
        answered_dims=answered_dims,
        turns=turns,
        capabilities=load_capabilities(db),
    )

    if decision.need_more_info and len(turns) < clarifier.max_turns:
        next_turn = ClarificationTurn(
            turn_index=len(turns) + 1,
            dim=decision.next_dim,
            question=decision.next_question,
        )
        turns.append(next_turn)
        record.turns = [turn.model_dump() for turn in turns]
        record.events = list(record.events) + [_build_question_event(next_turn)]
        store.save(record)
        return {"status": "accepted"}

    record.status = "generating"
    store.save(record)
    try:
        draft = planner.plan_with_answers(record.user_goal, answered_dims)
    except AgentPlanningError as exc:
        _finalize_session_to_failed(store=store, record=record, error=exc)
        return {"status": "accepted"}
    _finalize_session_to_ready(store=store, record=record, draft=draft)
    return {"status": "accepted"}


@router.post("/sessions/{session_id}/skip", status_code=202)
def skip_agent_session(
    session_id: str,
    db: Session = Depends(get_db),
):
    store = AgentSessionStore(db)
    planner = AgentPlanner(db)
    record = store.get_or_404(session_id)

    if record.status in {"ready", "applied"}:
        return {"status": "accepted"}
    if record.status != "clarifying":
        raise HTTPException(status_code=400, detail="Agent session cannot be skipped in its current state")

    record.status = "generating"
    store.save(record)
    try:
        draft = planner.plan_with_answers(record.user_goal, record.answered_dims)
    except AgentPlanningError as exc:
        _finalize_session_to_failed(store=store, record=record, error=exc)
        return {"status": "accepted"}
    _finalize_session_to_ready(store=store, record=record, draft=draft)
    return {"status": "accepted"}


@router.get("/sessions/{session_id}/events")
def stream_agent_session_events(
    session_id: str,
    replay_only: bool = Query(default=False),
    db: Session = Depends(get_db),
):
    store = AgentSessionStore(db)
    store.get_or_404(session_id)

    async def event_generator():
        sent_count = 0
        keepalive_ticks = 0

        while True:
            db.expire_all()
            record = store.get_or_404(session_id)
            events = record.events
            while sent_count < len(events):
                event = events[sent_count]
                sent_count += 1
                keepalive_ticks = 0
                yield (
                    f"event: {event['type']}\n"
                    f"data: {json.dumps(event, ensure_ascii=False)}\n\n"
                )

            if replay_only or record.status in {"ready", "applied", "failed"}:
                break

            await asyncio.sleep(0.5)
            keepalive_ticks += 1
            if keepalive_ticks >= 20:
                keepalive_ticks = 0
                yield ": keep-alive\n\n"

    return StreamingResponse(event_generator(), media_type="text/event-stream")


@router.post("/sessions/{session_id}/apply")
def apply_agent_session(
    session_id: str,
    db: Session = Depends(get_db),
):
    store = AgentSessionStore(db)
    record = store.get_or_404(session_id)

    if record.workflow_id:
        return {"workflow_id": record.workflow_id}
    if record.graph is None:
        raise HTTPException(status_code=400, detail="Agent session has no generated graph")

    compiler = GraphCompiler()
    try:
        compiler.validate(record.graph, db=db)
    except (CompilerError, ValueError, CycleDetectedError) as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    workflow = Workflow(
        name=_workflow_name_from_goal(record.user_goal),
        description="Generated by Agent mode",
    )
    workflow.graph = record.graph
    db.add(workflow)
    db.commit()
    db.refresh(workflow)

    store.mark_applied(record, workflow.id)
    return {"workflow_id": workflow.id}
