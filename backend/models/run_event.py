import json
from datetime import datetime, timezone

from sqlalchemy import Column, DateTime, ForeignKey, Integer, String, Text

from backend.database import Base


class WorkflowRunEvent(Base):
    __tablename__ = "workflow_run_events"

    id = Column(Integer, primary_key=True)
    workflow_id = Column(String, ForeignKey("workflows.id"), nullable=False)
    run_id = Column(String, ForeignKey("workflow_runs.id"), nullable=False)
    seq = Column(Integer, nullable=False)
    event_type = Column(String(64), nullable=False)
    event_json = Column(Text, default="{}", nullable=False)
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))

    @property
    def event(self) -> dict:
        return json.loads(self.event_json or "{}")

    @event.setter
    def event(self, value: dict):
        self.event_json = json.dumps(value, ensure_ascii=False)
