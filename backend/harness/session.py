"""PIAgent Harness v2 — HarnessSession: shell, lifecycle, SSE, pause/resume.

This module contains the orchestration loop and the HarnessSession class
that wraps a single "understand → build → validate → commit" attempt.
"""

from __future__ import annotations

import asyncio
import contextlib
import json
import uuid
from datetime import datetime, timezone
from typing import Any, Awaitable, Callable

from sqlalchemy import inspect, text
from sqlalchemy.orm import Session

from backend.harness.actions import BuilderError
from backend.harness.builder import GraphBuilder
from backend.harness.lead_agent import LeadAgent
from backend.harness.memory import EventLog
from backend.harness.preferences import PreferenceStore
from backend.harness.schemas import (
    AskUser,
    CallTool,
    Decision,
    Finalize,
    Finding,
    LoadSkill,
    ProposeAction,
)
from backend.harness.skills.loader import SkillLoader
from backend.harness.tools.base import HarnessContext, ToolRegistry
from backend.harness.validators import validate_graph
from backend.harness.workspace import Workspace
from backend.models.agent_session import AgentSession

EventCallback = Callable[[dict[str, Any]], Awaitable[None]]


def _decision_detail(decision: Decision) -> dict[str, Any]:
    """Produce a compact, JSON-safe payload describing a decision for the UI trace."""
    match decision:
        case CallTool(tool=name, args=args):
            return {"tool": name, "args": args}
        case LoadSkill(skill=name):
            return {"skill": name}
        case ProposeAction(action=action):
            return {
                "action_kind": action.kind,
                "action": action.model_dump(mode="json"),
                "summary": _action_summary(action),
            }
        case AskUser(question=q, options=opts):
            return {"question": q, "options": opts}
        case Finalize(reason=reason):
            return {"reason": reason}
        case _:
            return {}


def _action_summary(action: Any) -> str:
    """Short human-readable summary of a GraphAction."""
    kind = getattr(action, "kind", "?")
    if kind == "add_node":
        nid = action.node_id or f"<{action.node_type}>"
        return f"+ node {nid} ({action.node_type})"
    if kind == "add_edge":
        return f"+ edge {action.source} → {action.target}"
    if kind == "update_node_config":
        keys = ", ".join(action.config.keys()) or "(empty)"
        return f"~ {action.node_id} [{keys}]"
    if kind == "delete_node":
        return f"− node {action.node_id}"
    if kind == "delete_edge":
        return f"− edge {action.source} → {action.target}"
    return kind


class HarnessSession:
    """One complete harness attempt."""

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
        self.events = EventLog()
        self.tools = ToolRegistry()
        self.skills = SkillLoader()
        self.preferences = PreferenceStore(db)

        self._lead_agent: LeadAgent | None = None
        self._status: str = "running"  # running / awaiting_user / ready / failed / applied

    # ── setup ──

    def setup_tools(self, *tools: Any) -> None:
        for t in tools:
            self.tools.register(t)

    def init_lead_agent(self) -> None:
        self._lead_agent = LeadAgent(
            db=self.db,
            tool_registry=self.tools,
            skill_catalog=self.skills.catalog(),
            preferences=self.preferences.snapshot(),
        )

    # ── properties ──

    @property
    def status(self) -> str:
        return self._status

    @property
    def lead_agent(self) -> LeadAgent:
        if self._lead_agent is None:
            raise RuntimeError("LeadAgent not initialized. Call init_lead_agent() first.")
        return self._lead_agent

    # ── persistence helpers ──

    def _load_db(self) -> AgentSession | None:
        return self.db.query(AgentSession).filter(AgentSession.id == self.id).first()

    def _persist_workspace(self) -> None:
        row = self._load_db()
        if row is None:
            return
        row.workspace_json = json.dumps(self.workspace.to_snapshot(), ensure_ascii=False)
        row.status = self._status
        self.db.commit()

    def _persist_event(self, event_type: str, payload: dict) -> None:
        row = self._load_db()
        if row is None:
            return
        event = self.events.append(event_type, payload)
        # Always append to events_json for simplicity (dev SQLite)
        current = row.events or []
        if isinstance(current, str):
            current = json.loads(current)
        current.append(event)
        row.events_json = json.dumps(current, ensure_ascii=False)
        self.db.commit()

    # ── main loop ──

    async def run(self, on_event: EventCallback | None = None) -> None:
        """Execute the lead loop until completion, pause, or failure."""
        self.workspace.bootstrap(self.goal, preferences=self.preferences.snapshot())
        self._status = "running"
        self._persist_workspace()

        await self._emit("session_start", {"session_id": self.id, "goal": self.goal}, on_event)

        ctx = HarnessContext(db=self.db)
        last_stuck_checked_step = 0
        session_end_payload: dict[str, Any] | None = None

        try:
            while True:
                if self.workspace.budget_exhausted():
                    await self._emit(
                        "harness_stuck",
                        {"reason": "budget", "summary": "Step budget exhausted"},
                        on_event,
                    )
                    self._status = "failed"
                    break

                # Check stuck
                last_entry = self.workspace.trace.recent(window=1)
                if last_entry and last_entry[0].step != last_stuck_checked_step:
                    last_stuck_checked_step = last_entry[0].step
                    from pydantic import TypeAdapter
                    from backend.harness.schemas import Decision
                    last_dec = TypeAdapter(Decision).validate_python(last_entry[0].decision)
                    is_stuck = self.workspace.stuck.check(
                        decision=last_dec,
                        builder_error=None,
                        graph_changed=True,
                        tool_called=True,
                    )
                    if is_stuck:
                        summary = self.workspace.stuck_summary()
                        await self._emit("harness_stuck", {"reason": "stuck", "summary": summary}, on_event)
                        self._status = "failed"
                        break

                try:
                    decision = await asyncio.to_thread(self.lead_agent.decide, self.workspace)
                except TimeoutError as exc:
                    self.workspace.budget.used += 1
                    self.workspace.record_error("llm", str(exc))
                    await self._emit(
                        "llm_error",
                        {"phase": "decide", "message": str(exc), "recoverable": True},
                        on_event,
                    )
                    self._persist_workspace()
                    continue

                await self._emit("decision", {"kind": decision.kind, "detail": _decision_detail(decision)}, on_event)

                if isinstance(decision, LoadSkill) and self.workspace.has_loaded_skill(decision.skill):
                    self.workspace.budget.used += 1
                    cached_content = self.workspace.get_loaded_skill(decision.skill) or ""
                    self.workspace.record_error(
                        "skill",
                        f"{decision.skill} already loaded; use the loaded skill content in facts instead of loading it again",
                    )
                    await self._emit(
                        "skill_loaded",
                        {
                            "skill": decision.skill,
                            "cached": True,
                            "snippet": cached_content[:200],
                        },
                        on_event,
                    )
                    self._persist_workspace()
                    continue

                self.workspace.append_decision(decision)

                match decision:
                    case CallTool(tool=name, args=args):
                        await self._handle_call_tool(name, args, ctx, on_event)

                    case LoadSkill(skill=name):
                        await self._handle_load_skill(name, on_event)

                    case ProposeAction(action=action):
                        await self._handle_propose_action(action, on_event)

                    case AskUser(question=q, options=opts):
                        await self._handle_ask_user(q, opts, on_event)
                        return  # pause, caller must await resume()

                    case Finalize(reason=reason):
                        await self._handle_finalize(on_event)
                        if self._status == "ready":
                            return
                        # errors recorded, loop continues

                self._persist_workspace()

        except Exception as exc:
            self._status = "failed"
            session_end_payload = {"status": "failed", "reason": str(exc)}
            raise
        finally:
            self._persist_workspace()
            if self._status != "running":
                await self._emit("session_end", session_end_payload or {"status": self._status}, on_event)

    # ── decision handlers ──

    async def _handle_call_tool(
        self,
        name: str,
        args: dict,
        ctx: HarnessContext,
        on_event: EventCallback | None,
    ) -> None:
        await self._emit("tool_call", {"tool": name, "args": args}, on_event)
        try:
            tool = self.tools.get(name)
            input_model = tool.input_schema
            parsed = input_model.model_validate(args) if input_model is not type(None) else args
            result = await tool.run(parsed, ctx=ctx)
            self.workspace.record_fact(name, result)
            await self._emit(
                "tool_result",
                {"tool": name, "ok": True, "summary": result.model_dump_json()[:500]},
                on_event,
            )
        except Exception as exc:
            self.workspace.record_error("tool", f"{name}: {exc}")
            await self._emit("tool_result", {"tool": name, "ok": False, "error": str(exc)}, on_event)

    async def _handle_load_skill(self, name: str, on_event: EventCallback | None) -> None:
        try:
            content = self.skills.load(name)
            self.workspace.record_skill(name, content)
            await self._emit("skill_loaded", {"skill": name, "snippet": content[:200]}, on_event)
        except Exception as exc:
            self.workspace.record_error("skill", f"load {name}: {exc}")
            await self._emit("builder_error", {"message": f"Failed to load skill {name}: {exc}"}, on_event)

    async def _handle_propose_action(self, action, on_event: EventCallback | None) -> None:
        try:
            self.builder.apply(action)
            self.workspace.record_graph_update(self.builder.snapshot())
            snapshot = self.builder.snapshot()
            await self._emit(
                "graph_update",
                {
                    "snapshot": snapshot,
                    "action": action.model_dump(mode="json"),
                    "summary": _action_summary(action),
                    "node_count": len(snapshot["nodes"]),
                    "edge_count": len(snapshot["edges"]),
                },
                on_event,
            )
        except BuilderError as exc:
            self.workspace.record_error("builder", str(exc))
            await self._emit("builder_error", {"message": str(exc)}, on_event)

    async def _handle_ask_user(
        self,
        question: str,
        options: list[str] | None,
        on_event: EventCallback | None,
    ) -> None:
        qid = str(uuid.uuid4())
        self.workspace.set_open_question(question, options, question_id=qid)
        self._status = "awaiting_user"
        self._persist_workspace()
        await self._emit(
            "awaiting_user_input",
            {"question_id": qid, "prompt": question, "options": options},
            on_event,
        )

    async def _handle_finalize(self, on_event: EventCallback | None) -> None:
        findings = validate_graph(self.builder.snapshot(), db=self.db)
        self.workspace.record_validation(findings)
        await self._emit("validator_report", {"findings": [f.model_dump(mode="json") for f in findings]}, on_event)

        if not any(f.severity == "error" for f in findings):
            self._status = "ready"
            await self._emit("harness_ready", {"snapshot": self.builder.snapshot()}, on_event)
        # else: errors are in workspace facts, loop will continue

    # ── resume ──

    async def resume(self, question_id: str, answer: str, on_event: EventCallback | None = None) -> None:
        """Resume a paused session after the user answers an AskUser question."""
        await self.record_user_answer(question_id, answer, on_event=on_event)

        # Re-enter the loop
        await self.run(on_event=on_event)

    async def record_user_answer(
        self,
        question_id: str,
        answer: str,
        on_event: EventCallback | None = None,
    ) -> None:
        """Record an AskUser answer without advancing the lead loop."""
        if self._status != "awaiting_user":
            raise RuntimeError(f"Cannot resume: session status is {self._status}, not awaiting_user")

        open_question_id = (self.workspace.open_question or {}).get("question_id")
        if open_question_id and open_question_id != question_id:
            raise ValueError(f"Cannot resume: unknown question_id {question_id}")

        self.workspace.resolve_open_question(answer)
        self._status = "running"
        self._persist_workspace()
        await self._emit("user_resumed", {"question_id": question_id, "answer": answer}, on_event)

    # ── apply ──

    async def apply(self, workflow_id: str | None = None) -> dict:
        """Commit the ready graph to a Workflow and update preferences."""
        if self._status != "ready":
            raise RuntimeError(f"Cannot apply: session status is {self._status}, not ready")

        from backend.models.workflow import Workflow

        target_wfid = workflow_id or self.workflow_id
        if target_wfid is None:
            # Create a new workflow
            wf = Workflow(name=f"Harness: {self.goal[:40]}", graph_json=json.dumps(self.builder.snapshot(), ensure_ascii=False))
            self.db.add(wf)
            self.db.commit()
            target_wfid = str(wf.id)
        else:
            wf = self.db.query(Workflow).filter(Workflow.id == target_wfid).first()
            if wf is None:
                raise ValueError(f"Workflow not found: {target_wfid}")
            # Save the current graph (user may have edited it on canvas)
            # Note: in v2, canvas is read-only during session, so this is the harness draft
            wf.graph_json = json.dumps(self.builder.snapshot(), ensure_ascii=False)
            self.db.commit()

        self.workflow_id = target_wfid
        self._status = "applied"
        self._persist_workspace()

        # Preference learning
        self.preferences.learn_from_apply(
            harness_graph=self.builder.snapshot(),
            user_final_graph=self.builder.snapshot(),  # canvas locked during session
        )

        return {"workflow_id": target_wfid, "graph": self.builder.snapshot()}

    # ── abort ──

    def abort(self) -> None:
        self._status = "failed"
        self._persist_workspace()

    # ── internal ──

    async def _emit(self, event_type: str, payload: dict, on_event: EventCallback | None) -> None:
        self._persist_event(event_type, payload)
        if on_event is not None:
            await on_event({"type": event_type, **payload})


# ───────────────────────────────────────────────
# Factory
# ───────────────────────────────────────────────

def create_harness_session(
    db: Session,
    goal: str,
    workflow_id: str | None = None,
) -> HarnessSession:
    """Create a new HarnessSession and persist its AgentSession row."""
    session_id = str(uuid.uuid4())
    workspace_json = json.dumps({})
    created_at = datetime.now(timezone.utc)

    bind = db.get_bind()
    column_names = {
        column["name"] for column in inspect(bind).get_columns("agent_sessions")
    }

    if {"user_goal", "turns_json"} & column_names:
        values: dict[str, Any] = {
            "id": session_id,
            "goal": goal,
            "status": "running",
            "workspace_json": workspace_json,
            "events_json": "[]",
            "workflow_id": workflow_id,
            "created_at": created_at,
            "updated_at": created_at,
        }
        if "user_goal" in column_names:
            values["user_goal"] = goal
        if "turns_json" in column_names:
            values["turns_json"] = "[]"

        insert_columns = ", ".join(values.keys())
        insert_params = ", ".join(f":{key}" for key in values)
        db.execute(
            text(
                f"""
                INSERT INTO agent_sessions ({insert_columns})
                VALUES ({insert_params})
                """
            ),
            values,
        )
        db.commit()
    else:
        db_session = AgentSession(
            id=session_id,
            goal=goal,
            status="running",
            workspace_json=workspace_json,
            events_json="[]",
            workflow_id=workflow_id,
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
    """Restore a HarnessSession from its DB row."""
    row = db.query(AgentSession).filter(AgentSession.id == session_id).first()
    if row is None:
        raise ValueError(f"Session not found: {session_id}")

    hs = HarnessSession(
        session_id=row.id,
        db=db,
        goal=row.goal,
        workflow_id=row.workflow_id,
    )
    if row.workspace_json:
        hs.workspace.from_snapshot(json.loads(row.workspace_json))
        hs.builder.from_snapshot(hs.workspace.graph_draft)
    hs._status = row.status
    return hs
