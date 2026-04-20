from __future__ import annotations

import json
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Awaitable, Callable

from langchain_core.messages import AIMessage, HumanMessage, ToolMessage
from sqlalchemy.orm import Session

from backend.models.agent_session import AgentSession
from backend.models.workflow import Workflow
from backend.pi_harness.adapters.provider_bridge import DBModelResolver
from backend.pi_harness.adapters.session_store import (
    dump_workspace_state,
    load_workspace_state,
)
from backend.pi_harness.adapters.sse_bridge import (
    parse_clarification_payload,
    summarize_tool_output,
)
from backend.pi_harness.runtime.agent.graph import create_agent
from backend.pi_harness.state import WorkflowGraphDraft
from backend.pi_harness.tools.context import build_context_tools
from backend.pi_harness.tools.finalize import build_finalize_draft_tool
from backend.pi_harness.tools.graph_ops import build_graph_op_tools
from backend.pi_harness.tools.validate import build_validate_graph_tool

EventCallback = Callable[[dict[str, Any]], Awaitable[None]]
_SKILLS_PATH = Path(__file__).resolve().parent / "skills"
_SYSTEM_PROMPT = (
    "You are PIAgent's workflow-building harness. "
    "Use the available tools to inspect capabilities, incrementally build a valid workflow graph, "
    "ask for clarification instead of guessing when required, and call finalize_draft when the graph is valid."
)


class HarnessSession:
    """Session orchestration layer for the pi_harness runtime."""

    def __init__(
        self,
        session_id: str,
        db: Session,
        goal: str,
        workflow_id: str | None = None,
    ):
        self.id = session_id
        self.db = db
        self.goal = goal
        self.workflow_id = workflow_id

        self.draft = WorkflowGraphDraft()
        self.messages: list = []
        self.open_question: dict[str, Any] | None = None
        self._status: str = "running"
        self._pending_events: list[dict[str, Any]] = []

    @property
    def status(self) -> str:
        return self._status

    def _queue_event(self, event: dict[str, Any]) -> None:
        self._pending_events.append(event)

    def _load_db(self) -> AgentSession | None:
        return self.db.query(AgentSession).filter(AgentSession.id == self.id).first()

    def _persist_workspace(self) -> None:
        row = self._load_db()
        if row is None:
            return
        row.workspace_json = dump_workspace_state(
            messages=self.messages,
            graph=self.draft.snapshot(),
            open_question=self.open_question,
            status=self._status,
        )
        row.status = self._status
        row.workflow_id = self.workflow_id
        self.db.commit()

    def _persist_event(self, event_type: str, payload: dict[str, Any]) -> None:
        row = self._load_db()
        if row is None:
            return
        event = {"type": event_type, **payload}
        current = row.events or []
        if isinstance(current, str):
            current = json.loads(current)
        current.append(event)
        row.events_json = json.dumps(current, ensure_ascii=False)
        self.db.commit()

    async def _emit(self, event_type: str, payload: dict[str, Any], on_event: EventCallback | None) -> None:
        self._persist_event(event_type, payload)
        if on_event is not None:
            await on_event({"type": event_type, **payload})

    async def _flush_pending_events(self, on_event: EventCallback | None) -> None:
        while self._pending_events:
            event = self._pending_events.pop(0)
            event_type = event.pop("type")
            await self._emit(event_type, event, on_event)

    def _build_agent(self):
        resolver = DBModelResolver(self.db)

        def _mark_ready(graph: dict) -> None:
            self._status = "ready"
            self._queue_event({"type": "harness_ready", "snapshot": graph})

        tools = [
            *build_context_tools(self.db),
            *build_graph_op_tools(self.draft, event_sink=self._queue_event),
            build_validate_graph_tool(self.draft, db=self.db),
            build_finalize_draft_tool(self.draft, db=self.db, on_ready=_mark_ready),
        ]

        return create_agent(
            model=resolver.get_model(),
            tool_instances=tools,
            system_prompt=_SYSTEM_PROMPT,
            skills_path=_SKILLS_PATH,
        )

    async def run(self, on_event: EventCallback | None = None) -> None:
        if not self.messages:
            self.messages = [HumanMessage(content=self.goal)]

        self._status = "running"
        self._persist_workspace()
        await self._emit("session_start", {"session_id": self.id, "goal": self.goal}, on_event)

        agent = self._build_agent()
        # When resuming a paused session, the stored transcript already contains
        # prior tool calls and clarification messages. Start diffing from the
        # current transcript length so we only emit newly-generated messages.
        last_message_count = len(self.messages)
        session_end_payload: dict[str, Any] | None = None

        try:
            async for state in agent.astream({"messages": self.messages}, stream_mode="values"):
                messages = list(state["messages"])
                new_messages = messages[last_message_count:]

                for message in new_messages:
                    if isinstance(message, AIMessage) and message.tool_calls:
                        for tool_call in message.tool_calls:
                            await self._emit(
                                "tool_call",
                                {
                                    "tool": tool_call.get("name"),
                                    "args": tool_call.get("args", {}),
                                    "call_id": tool_call.get("id"),
                                },
                                on_event,
                            )
                    elif isinstance(message, ToolMessage):
                        clarification = parse_clarification_payload(message.content)
                        if clarification is not None:
                            question_id = str(uuid.uuid4())
                            self.open_question = {
                                "question_id": question_id,
                                "prompt": clarification.get("question", ""),
                                "options": clarification.get("options") or None,
                            }
                            self.messages = messages
                            self._status = "awaiting_user"
                            self._persist_workspace()
                            await self._flush_pending_events(on_event)
                            await self._emit(
                                "awaiting_user_input",
                                {
                                    "question_id": question_id,
                                    "prompt": clarification.get("question", ""),
                                    "options": clarification.get("options") or None,
                                },
                                on_event,
                            )
                            return

                        await self._emit(
                            "tool_result",
                            {
                                "tool": message.name,
                                "ok": True,
                                "call_id": message.tool_call_id,
                                "summary": summarize_tool_output(message.content),
                            },
                            on_event,
                        )

                self.messages = messages
                last_message_count = len(messages)
                await self._flush_pending_events(on_event)
                self._persist_workspace()

                if self._status == "ready":
                    return

            if self._status == "running":
                self._status = "failed"
                session_end_payload = {
                    "status": "failed",
                    "reason": "agent completed without finalizing a draft",
                }
        except Exception as exc:
            self._status = "failed"
            session_end_payload = {"status": "failed", "reason": str(exc)}
        finally:
            self._persist_workspace()
            if self._status in {"ready", "failed", "applied"}:
                await self._emit(
                    "session_end",
                    session_end_payload or {"status": self._status},
                    on_event,
                )

    async def record_user_answer(
        self,
        question_id: str,
        answer: str,
        on_event: EventCallback | None = None,
    ) -> None:
        if self._status != "awaiting_user":
            raise RuntimeError(f"Cannot resume: session status is {self._status}, not awaiting_user")

        current_question_id = (self.open_question or {}).get("question_id")
        if current_question_id and current_question_id != question_id:
            raise ValueError(f"Cannot resume: unknown question_id {question_id}")

        self.messages.append(HumanMessage(content=answer))
        self.open_question = None
        self._status = "running"
        self._persist_workspace()
        await self._emit("user_resumed", {"question_id": question_id, "answer": answer}, on_event)

    async def apply(self, workflow_id: str | None = None) -> dict[str, Any]:
        if self._status != "ready":
            raise RuntimeError(f"Cannot apply: session status is {self._status}, not ready")

        target_workflow_id = workflow_id or self.workflow_id
        graph = self.draft.snapshot()

        if target_workflow_id is None:
            workflow = Workflow(name=f"Harness: {self.goal[:40]}")
            workflow.graph = graph
            self.db.add(workflow)
            self.db.commit()
            target_workflow_id = str(workflow.id)
        else:
            workflow = self.db.query(Workflow).filter(Workflow.id == target_workflow_id).first()
            if workflow is None:
                raise ValueError(f"Workflow not found: {target_workflow_id}")
            workflow.graph = graph
            self.db.commit()

        self.workflow_id = target_workflow_id
        self._status = "applied"
        self._persist_workspace()
        return {"workflow_id": target_workflow_id, "graph": graph}

    def abort(self) -> None:
        self._status = "failed"
        self._persist_workspace()


def create_harness_session(
    db: Session,
    goal: str,
    workflow_id: str | None = None,
) -> HarnessSession:
    session_id = str(uuid.uuid4())
    db_session = AgentSession(
        id=session_id,
        goal=goal,
        status="running",
        workspace_json=dump_workspace_state(
            messages=[],
            graph={"version": 2, "nodes": [], "edges": []},
            open_question=None,
            status="running",
        ),
        events_json="[]",
        workflow_id=workflow_id,
        created_at=datetime.now(timezone.utc),
    )
    db.add(db_session)
    db.commit()

    return HarnessSession(
        session_id=session_id,
        db=db,
        goal=goal,
        workflow_id=workflow_id,
    )


def load_harness_session(session_id: str, db: Session) -> HarnessSession:
    row = db.query(AgentSession).filter(AgentSession.id == session_id).first()
    if row is None:
        raise ValueError(f"Session not found: {session_id}")

    session = HarnessSession(
        session_id=row.id,
        db=db,
        goal=row.goal,
        workflow_id=row.workflow_id,
    )
    state = load_workspace_state(row.workspace_json)
    session.messages = state["messages"]
    session.draft.load_snapshot(state["graph"])
    session.open_question = state["open_question"]
    session._status = row.status or state["status"]
    return session
