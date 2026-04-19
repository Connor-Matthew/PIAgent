"""PIAgent Harness v2 — Workspace: mutable workbench for a single harness session.

Holds the graph draft, accumulated facts, decision trace, open questions, and budget.
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any

from pydantic import BaseModel

from backend.harness.schemas import Decision, Finding


# ───────────────────────────────────────────────
# Budget
# ───────────────────────────────────────────────

@dataclass
class Budget:
    used: int = 0
    cap: int = 50

    def exhausted(self) -> bool:
        return self.used >= self.cap

    def remaining(self) -> int:
        return max(0, self.cap - self.used)

    def to_dict(self) -> dict:
        return {"used": self.used, "cap": self.cap, "remaining": self.remaining()}


# ───────────────────────────────────────────────
# FactsLedger
# ───────────────────────────────────────────────

class FactsLedger:
    """Deduplicated, compressible store of tool results, skills, errors, and validation findings."""

    def __init__(self) -> None:
        self._tool_results: list[dict] = []
        self._skills: dict[str, str] = {}
        self._errors: list[dict] = []
        self._validation_findings: list[dict] = []

    def record_tool_result(self, tool_name: str, result: BaseModel) -> None:
        entry = {
            "type": "tool_result",
            "tool": tool_name,
            "result": result.model_dump(mode="json"),
        }
        self._tool_results.append(entry)

    def record_skill(self, skill_name: str, content: str) -> None:
        self._skills[skill_name] = content

    def has_skill(self, skill_name: str) -> bool:
        return skill_name in self._skills

    def get_skill(self, skill_name: str) -> str | None:
        return self._skills.get(skill_name)

    def record_error(self, source: str, message: str) -> None:
        self._errors.append({"type": "error", "source": source, "message": message})

    def record_validation(self, findings: list[Finding]) -> None:
        for f in findings:
            self._validation_findings.append(f.model_dump(mode="json"))

    def to_dict(self) -> dict:
        return {
            "tool_results": list(self._tool_results),
            "skills": dict(self._skills),
            "errors": list(self._errors),
            "validation_findings": list(self._validation_findings),
        }

    def from_dict(self, data: dict) -> None:
        self._tool_results = list(data.get("tool_results", []))
        self._skills = dict(data.get("skills", {}))
        self._errors = list(data.get("errors", []))
        self._validation_findings = list(data.get("validation_findings", []))

    def render(self) -> str:
        """Render facts into a concise observation string for the LLM."""
        parts: list[str] = []

        if self._tool_results:
            parts.append("## Tool Results")
            for entry in self._tool_results:
                parts.append(f"- {entry['tool']}: {json.dumps(entry['result'], ensure_ascii=False, indent=2)}")

        if self._skills:
            parts.append("## Loaded Skills")
            parts.append(
                "Loaded skill content is already in context. "
                "Do not call load_skill again for a skill listed here."
            )
            for name, content in self._skills.items():
                parts.append(f"### {name}")
                parts.append(content)

        if self._errors:
            parts.append("## Errors")
            for entry in self._errors:
                parts.append(f"- [{entry['source']}] {entry['message']}")

        if self._validation_findings:
            parts.append("## Validation Findings")
            for f in self._validation_findings:
                sev = f.get("severity", "error")
                msg = f.get("message", "")
                parts.append(f"- [{sev.upper()}] {msg}")

        return "\n".join(parts) if parts else "(no facts yet)"


# ───────────────────────────────────────────────
# Trace
# ───────────────────────────────────────────────

@dataclass
class TraceEntry:
    step: int
    timestamp: str
    decision: dict
    result: dict | None = None


class Trace:
    def __init__(self) -> None:
        self._entries: list[TraceEntry] = []

    def append(self, decision: Decision, result: dict | None = None) -> None:
        entry = TraceEntry(
            step=len(self._entries) + 1,
            timestamp=datetime.now(timezone.utc).isoformat(),
            decision=decision.model_dump(mode="json"),
            result=result,
        )
        self._entries.append(entry)

    def recent(self, window: int = 5) -> list[TraceEntry]:
        return self._entries[-window:]

    def to_dict(self) -> list[dict]:
        return [
            {
                "step": e.step,
                "timestamp": e.timestamp,
                "decision": e.decision,
                "result": e.result,
            }
            for e in self._entries
        ]

    def from_dict(self, data: list[dict]) -> None:
        self._entries = [
            TraceEntry(
                step=e["step"],
                timestamp=e["timestamp"],
                decision=e["decision"],
                result=e.get("result"),
            )
            for e in data
        ]

    def last_decision_hash(self) -> str | None:
        if not self._entries:
            return None
        raw = json.dumps(self._entries[-1].decision, sort_keys=True)
        return hashlib.sha256(raw.encode()).hexdigest()[:16]


# ───────────────────────────────────────────────
# StuckDetector
# ───────────────────────────────────────────────

class StuckDetector:
    """Detects when the lead loop is stuck and should escalate to AskUser."""

    def __init__(self) -> None:
        self._last_hashes: list[str] = []
        self._last_builder_errors: list[str] = []
        self._steps_since_change: int = 0

    def check(
        self,
        decision: Decision,
        builder_error: str | None = None,
        graph_changed: bool = True,
        tool_called: bool = True,
    ) -> bool:
        """Return True if the loop appears stuck."""
        # Hash-based: consecutive identical decisions
        raw = decision.model_dump_json()
        h = hashlib.sha256(raw.encode()).hexdigest()[:16]
        self._last_hashes.append(h)
        if len(self._last_hashes) > 3:
            self._last_hashes.pop(0)

        # Builder error repetition
        if builder_error:
            self._last_builder_errors.append(builder_error)
            if len(self._last_builder_errors) > 4:
                self._last_builder_errors.pop(0)
        else:
            self._last_builder_errors = []

        # Steps without graph change or new tool call
        if graph_changed or tool_called:
            self._steps_since_change = 0
        else:
            self._steps_since_change += 1

        # Rule 1: 2 consecutive identical decision hashes
        if len(self._last_hashes) >= 2 and self._last_hashes[-1] == self._last_hashes[-2]:
            return True

        # Rule 2: 3 consecutive same builder errors
        if len(self._last_builder_errors) >= 3:
            if self._last_builder_errors[-1] == self._last_builder_errors[-2] == self._last_builder_errors[-3]:
                return True

        # Rule 3: 5 steps with no graph change and no new tool call
        if self._steps_since_change >= 5:
            return True

        return False

    def summary(self) -> str:
        reasons: list[str] = []
        if len(self._last_hashes) >= 2 and self._last_hashes[-1] == self._last_hashes[-2]:
            reasons.append("repeated decision")
        if len(self._last_builder_errors) >= 3:
            reasons.append("repeated builder errors")
        if self._steps_since_change >= 5:
            reasons.append("no progress for 5 steps")
        return "; ".join(reasons) if reasons else "unknown"


# ───────────────────────────────────────────────
# Observation
# ───────────────────────────────────────────────

@dataclass
class Observation:
    """Rendered snapshot of workspace state, fed to the LLM each turn."""

    goal: str
    facts: str
    current_graph: dict
    open_question: dict | None
    budget_remaining: int
    recent_trace: list[dict]

    def render(self) -> str:
        parts: list[str] = []
        parts.append(f"# Goal\n{self.goal}\n")

        if self.open_question:
            parts.append(f"# Awaiting User Reply\nQuestion: {self.open_question.get('question', '')}\n")

        parts.append(f"# Budget\nRemaining steps: {self.budget_remaining}\n")

        if self.recent_trace:
            parts.append("# Recent Trace")
            for entry in self.recent_trace:
                dec = entry.get("decision", {})
                kind = dec.get("kind", "?")
                parts.append(f"- step {entry.get('step', '?')}: {kind}")
            parts.append("")

        parts.append(f"# Current Graph\n{json.dumps(self.current_graph, ensure_ascii=False, indent=2)}\n")

        parts.append(f"# Facts\n{self.facts}\n")

        return "\n".join(parts)


# ───────────────────────────────────────────────
# Workspace
# ───────────────────────────────────────────────

class Workspace:
    """Mutable workbench for a single harness session."""

    def __init__(self, goal: str = "", preferences: dict | None = None) -> None:
        self.goal: str = goal
        self.preferences: dict = preferences or {}
        self.facts = FactsLedger()
        self.trace = Trace()
        self.stuck = StuckDetector()
        self.budget = Budget()
        self.graph_draft: dict = {"nodes": [], "edges": []}
        self.open_question: dict | None = None

    def bootstrap(self, goal: str, preferences: dict | None = None) -> None:
        self.goal = goal
        self.preferences = preferences or {}
        # Pre-seed preferences into facts so the LLM sees them
        if self.preferences:
            self.facts.record_tool_result(
                "recall_preference",
                _PreferencesResult(preferences=self.preferences),
            )

    def budget_exhausted(self) -> bool:
        return self.budget.exhausted()

    def is_stuck(self, decision: Decision, builder_error: str | None = None, graph_changed: bool = True, tool_called: bool = True) -> bool:
        """Check if the loop appears stuck using StuckDetector rules.

        Args:
            decision: The most recent decision.
            builder_error: Optional builder error message from the last action.
            graph_changed: Whether the graph draft changed in the last step.
            tool_called: Whether a new tool was called in the last step.
        """
        return self.stuck.check(decision, builder_error, graph_changed, tool_called)

    def stuck_summary(self) -> str:
        return self.stuck.summary()

    def observation(self) -> Observation:
        return Observation(
            goal=self.goal,
            facts=self.facts.render(),
            current_graph=self.graph_draft,
            open_question=self.open_question,
            budget_remaining=self.budget.remaining(),
            recent_trace=[
                {"step": e.step, "decision": e.decision}
                for e in self.trace.recent(window=5)
            ],
        )

    def append_decision(self, decision: Decision) -> None:
        self.trace.append(decision)
        self.budget.used += 1

    def record_fact(self, tool_name: str, result: BaseModel) -> None:
        self.facts.record_tool_result(tool_name, result)

    def record_skill(self, skill_name: str, content: str) -> None:
        self.facts.record_skill(skill_name, content)

    def has_loaded_skill(self, skill_name: str) -> bool:
        return self.facts.has_skill(skill_name)

    def get_loaded_skill(self, skill_name: str) -> str | None:
        return self.facts.get_skill(skill_name)

    def record_graph_update(self, snapshot: dict) -> None:
        self.graph_draft = dict(snapshot)

    def record_error(self, source: str, message: str) -> None:
        self.facts.record_error(source, message)

    def record_validation(self, findings: list[Finding]) -> None:
        self.facts.record_validation(findings)

    def set_open_question(self, question: str, options: list[str] | None = None, question_id: str = "") -> None:
        self.open_question = {
            "question": question,
            "options": options,
            "question_id": question_id,
        }

    def resolve_open_question(self, answer: str) -> None:
        # Record the answer as a fact, then clear the open question
        if self.open_question:
            self.facts.record_tool_result(
                "user_reply",
                _UserReplyResult(
                    question=self.open_question.get("question", ""),
                    answer=answer,
                ),
            )
        self.open_question = None

    # ── snapshot / restore ──

    def to_snapshot(self) -> dict:
        return {
            "goal": self.goal,
            "preferences": self.preferences,
            "facts": self.facts.to_dict(),
            "trace": self.trace.to_dict(),
            "graph_draft": dict(self.graph_draft),
            "open_question": self.open_question,
            "budget": self.budget.to_dict(),
        }

    def from_snapshot(self, data: dict) -> None:
        self.goal = data.get("goal", "")
        self.preferences = data.get("preferences", {})
        self.facts.from_dict(data.get("facts", {}))
        self.trace.from_dict(data.get("trace", []))
        self.graph_draft = dict(data.get("graph_draft", {"nodes": [], "edges": []}))
        self.open_question = data.get("open_question")
        budget_data = data.get("budget", {})
        self.budget = Budget(
            used=budget_data.get("used", 0),
            cap=budget_data.get("cap", 50),
        )


# ── tiny Pydantic models for internal fact recording ──

class _PreferencesResult(BaseModel):
    preferences: dict


class _UserReplyResult(BaseModel):
    question: str
    answer: str
