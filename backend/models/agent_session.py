import json
import uuid
from datetime import datetime, timezone

from sqlalchemy import Column, DateTime, ForeignKey, String, Text

from backend.database import Base


class AgentSession(Base):
    __tablename__ = "agent_sessions"

    id = Column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    goal = Column(Text, nullable=False)
    status = Column(String(32), nullable=False, default="running")
    workspace_json = Column(Text, nullable=True)
    events_json = Column(Text, nullable=False, default="[]")
    messages_json = Column(Text, nullable=False, default="[]")
    workflow_id = Column(String, ForeignKey("workflows.id"), nullable=True)
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))
    updated_at = Column(
        DateTime,
        default=lambda: datetime.now(timezone.utc),
        onupdate=lambda: datetime.now(timezone.utc),
    )

    @property
    def events(self) -> list[dict]:
        return json.loads(self.events_json or "[]")

    @events.setter
    def events(self, value: list[dict]):
        self.events_json = json.dumps(value or [], ensure_ascii=False)
