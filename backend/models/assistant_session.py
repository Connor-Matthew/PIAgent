import json
from datetime import datetime, timezone

from sqlalchemy import Column, DateTime, ForeignKey, Integer, String, Text

from backend.database import Base


class AssistantSession(Base):
    __tablename__ = "assistant_sessions"

    id = Column(Integer, primary_key=True)
    workflow_id = Column(String, ForeignKey("workflows.id"), nullable=False, unique=True)
    messages_json = Column(Text, default="[]", nullable=False)
    updated_at = Column(
        DateTime,
        default=lambda: datetime.now(timezone.utc),
        onupdate=lambda: datetime.now(timezone.utc),
    )

    @property
    def messages(self) -> list[dict]:
        return json.loads(self.messages_json or "[]")

    @messages.setter
    def messages(self, value: list[dict]):
        self.messages_json = json.dumps(value, ensure_ascii=False)
