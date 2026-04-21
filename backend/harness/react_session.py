"""PIAgent ReAct Builder Agent — Session lifecycle, persistence, SSE.

Replaces the Decision-loop HarnessSession with a ReAct-runner-based session.
"""

from __future__ import annotations

import json
import uuid
from datetime import datetime, timezone
from typing import Any, Awaitable, Callable

from langchain_core.messages import AIMessage, HumanMessage, SystemMessage, ToolMessage
from sqlalchemy.orm import Session

from backend.harness.builder import GraphBuilder
from backend.harness.react_runner import ReActBuilderAgentRunner
from backend.harness.skills.loader import SkillLoader
from backend.harness.workspace import Workspace
from backend.models.agent_session import AgentSession

EventCallback = Callable[[dict[str, Any]], Awaitable[None]]


def _messages_to_json(messages: list[Any]) -> str:
    """Serialize LangChain messages to JSON for persistence."""
    serializable = []
    for m in messages:
        item: dict[str, Any] = {
            "type": m.type if hasattr(m, "type") else "unknown",
            "content": m.content,
        }
        if isinstance(m, AIMessage):
            if m.tool_calls:
                item["tool_calls"] = m.tool_calls
        if isinstance(m, ToolMessage):
            item["tool_call_id"] = m.tool_call_id
            item["name"] = m.name
        serializable.append(item)
    return json.dumps(serializable, ensure_ascii=False)


def _messages_from_json(text: str) -> list[HumanMessage | AIMessage | ToolMessage]:
    """Deserialize JSON back to LangChain messages."""
    data = json.loads(text or "[]")
    messages = []
    for item in data:
        msg_type = item.get("type", "")
        content = item.get("content", "")
        if msg_type == "system":
            messages.append(SystemMessage(content=content))
        elif msg_type in ("ai", "assistant"):
            tc = item.get("tool_calls")
            messages.append(AIMessage(content=content, tool_calls=tc))
        elif msg_type == "tool":
            messages.append(ToolMessage(
                content=content,
                tool_call_id=item.get("tool_call_id", ""),
                name=item.get("name", ""),
            ))
        else:
            messages.append(HumanMessage(content=content))
    return messages


class ReActHarnessSession:
    """One complete harness attempt powered by ReActBuilderAgentRunner."""

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

        self.workspace = Workspace()
        self.builder = GraphBuilder()
        self.skills = SkillLoader()

        self._runner: ReActBuilderAgentRunner | None = None
        self._status: str = "running"
        self._messages: list[HumanMessage | AIMessage | ToolMessage] = []

    # ── properties ──

    @property
    def status(self) -> str:
        return self._status

    @property
    def messages(self) -> list[HumanMessage | AIMessage | ToolMessage]:
        return list(self._messages)

    @property
    def runner(self) -> ReActBuilderAgentRunner:
        if self._runner is None:
            self._init_runner()
        return self._runner

    def _init_runner(self) -> None:
        self._runner = ReActBuilderAgentRunner(
            session_id=self.id,
            workspace=self.workspace,
            builder=self.builder,
            db=self.db,
            skills=self.skills,
        )

    # ── persistence helpers ──

    def _load_db(self) -> AgentSession | None:
        return self.db.query(AgentSession).filter(AgentSession.id == self.id).first()

    def _persist(self) -> None:
        row = self._load_db()
        if row is None:
            return
        row.workspace_json = json.dumps(self.workspace.to_snapshot(), ensure_ascii=False)
        row.status = self._status
        row.messages_json = _messages_to_json(self._messages)
        self.db.commit()

    # ── main loop ──

    async def run(self, on_event: EventCallback | None = None) -> None:
        """Start or continue the ReAct stream."""
        self.workspace.bootstrap(self.goal, preferences={})
        self._status = "running"
        self._persist()

        # If first run, prepend the goal as a human message
        if not self._messages:
            self._messages.append(HumanMessage(content=self.goal))

        # Wrap on_event to capture state transitions
        _ready_seen = False
        _paused_seen = False
        _terminal_event_sent = False

        async def _wrapped_emit(event: dict) -> None:
            nonlocal _ready_seen, _paused_seen
            etype = event.get("type", "")
            if etype == "harness_ready":
                _ready_seen = True
                self._status = "ready"
                self._persist()
            if etype == "awaiting_user_input":
                _paused_seen = True
                self._status = "awaiting_user"
                self._persist()
            if on_event is not None:
                await on_event(event)

        try:
            final_messages = await self.runner.run(
                messages=self._messages,
                on_event=_wrapped_emit,
            )
            self._messages = final_messages

            # Update status based on captured events
            if _paused_seen or self.workspace.open_question:
                self._status = "awaiting_user"
            elif _ready_seen:
                self._status = "ready"
            else:
                self._status = "waiting"

        except Exception as exc:
            self._status = "failed"
            if on_event is not None:
                await on_event({"type": "session_end", "status": "failed", "reason": str(exc)})
                _terminal_event_sent = True
            raise
        finally:
            self._persist()
            if self._status != "running" and not _terminal_event_sent:
                if on_event is not None:
                    await on_event({"type": "session_end", "status": self._status})

    # ── resume ──

    def queue_resume(self, question_id: str, answer: str) -> None:
        """Record an answer to an open question so the SSE stream can run the next turn."""
        if self._status != "awaiting_user":
            raise RuntimeError(f"Cannot resume: session status is {self._status}, not awaiting_user")

        if not self.workspace.open_question:
            raise RuntimeError("Cannot resume: session has no open question")

        open_question_id = self.workspace.open_question.get("question_id")
        if open_question_id and open_question_id != question_id:
            raise ValueError(f"Cannot resume: unknown question_id {question_id}")

        self.workspace.resolve_open_question(answer)
        self._messages.append(HumanMessage(content=f"User answered: {answer}"))
        self._status = "running"
        self._persist()

    def queue_user_message(self, message: str) -> None:
        """Record a normal follow-up message so the SSE stream can run the next turn."""
        if self._status not in ("awaiting_user", "waiting", "ready"):
            raise RuntimeError(f"Cannot continue: session status is {self._status}")
        if self.workspace.open_question:
            raise RuntimeError("Cannot continue: answer the open question first")

        self._messages.append(HumanMessage(content=message))
        self._status = "running"
        self._persist()

    async def resume(self, question_id: str, answer: str, on_event: EventCallback | None = None) -> None:
        """Resume after an ask_user pause."""
        self.queue_resume(question_id, answer)

        if on_event is not None:
            await on_event({"type": "user_resumed", "question_id": question_id, "answer": answer})

        await self.run(on_event=on_event)

    # ── apply ──

    async def apply(self, workflow_id: str | None = None) -> dict:
        """Commit the ready graph to a Workflow."""
        if self._status != "ready":
            raise RuntimeError(f"Cannot apply: session status is {self._status}, not ready")

        from backend.models.workflow import Workflow

        target_wfid = workflow_id or self.workflow_id
        if target_wfid is None:
            wf = Workflow(name=f"Harness: {self.goal[:40]}")
            wf.graph = self.builder.snapshot()
            self.db.add(wf)
            self.db.commit()
            target_wfid = str(wf.id)
        else:
            wf = self.db.query(Workflow).filter(Workflow.id == target_wfid).first()
            if wf is None:
                raise ValueError(f"Workflow not found: {target_wfid}")
            wf.graph = self.builder.snapshot()
            self.db.commit()

        self.workflow_id = target_wfid
        self._status = "applied"
        self._persist()
        return {"workflow_id": target_wfid, "graph": self.builder.snapshot()}

    # ── abort ──

    def abort(self) -> None:
        self._status = "failed"
        self._persist()


# ───────────────────────────────────────────────
# Factory
# ───────────────────────────────────────────────


def create_react_harness_session(
    db: Session,
    goal: str,
    workflow_id: str | None = None,
) -> ReActHarnessSession:
    """Create a new ReActHarnessSession and persist its AgentSession row."""
    session_id = str(uuid.uuid4())
    created_at = datetime.now(timezone.utc)

    db_session = AgentSession(
        id=session_id,
        goal=goal,
        status="running",
        workspace_json="{}",
        events_json="[]",
        messages_json="[]",
        workflow_id=workflow_id,
    )
    db.add(db_session)
    db.commit()

    return ReActHarnessSession(
        session_id=session_id,
        db=db,
        goal=goal,
        workflow_id=workflow_id,
    )


def load_react_harness_session(session_id: str, db: Session) -> ReActHarnessSession:
    """Restore a ReActHarnessSession from its DB row."""
    row = db.query(AgentSession).filter(AgentSession.id == session_id).first()
    if row is None:
        raise ValueError(f"Session not found: {session_id}")

    hs = ReActHarnessSession(
        session_id=row.id,
        db=db,
        goal=row.goal,
        workflow_id=row.workflow_id,
    )
    if row.workspace_json:
        snapshot = json.loads(row.workspace_json)
        hs.workspace.from_snapshot(snapshot)
        hs.builder.from_snapshot(hs.workspace.graph_draft)
    # Restore messages from dedicated column (preferred) or legacy snapshot embedding
    if row.messages_json and row.messages_json != "[]":
        hs._messages = _messages_from_json(row.messages_json)
    elif row.workspace_json:
        snapshot = json.loads(row.workspace_json)
        msgs_json = snapshot.pop("_messages", None)
        if msgs_json:
            hs._messages = _messages_from_json(msgs_json)
    hs._status = row.status
    if hs._status == "awaiting_user" and not hs.workspace.open_question:
        hs._status = "waiting"
    return hs
