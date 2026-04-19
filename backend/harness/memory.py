"""PIAgent Harness v2 — WorkspaceSnapshotStore + EventLog.

Workspace snapshot is the source of truth for session resumption.
Event log is an audit trail for UI replay.
"""

from __future__ import annotations

import json
from datetime import datetime, timezone

from backend.harness.workspace import Workspace


class EventLog:
    """In-memory event buffer with periodic flush strategy.

    Durable events (session_start, awaiting_user_input, user_resumed,
    harness_ready, session_end, validator_report) should be flushed immediately.
    Ephemeral events are buffered and flushed on state transitions.
    """

    DURABLE_TYPES: set[str] = {
        "session_start",
        "awaiting_user_input",
        "user_resumed",
        "harness_ready",
        "session_end",
        "validator_report",
    }

    def __init__(self) -> None:
        self._events: list[dict] = []

    def append(self, event_type: str, payload: dict) -> dict:
        event = {
            "type": event_type,
            "payload": payload,
            "ts": datetime.now(timezone.utc).isoformat(),
        }
        self._events.append(event)
        return event

    def is_durable(self, event_type: str) -> bool:
        return event_type in self.DURABLE_TYPES

    def flush(self) -> list[dict]:
        """Return all events and clear the buffer."""
        out = list(self._events)
        self._events = []
        return out

    def to_list(self) -> list[dict]:
        return list(self._events)
