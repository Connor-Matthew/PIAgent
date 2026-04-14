import json
from datetime import datetime, timezone
from sqlalchemy import Column, String, Text, Float, DateTime, ForeignKey
from backend.database import Base
import uuid


class _RunOutputEncoder(json.JSONEncoder):
    def default(self, obj):
        if hasattr(obj, "model_dump"):
            return obj.model_dump()
        if hasattr(obj, "dict"):
            return obj.dict()
        return super().default(obj)


class WorkflowRun(Base):
    __tablename__ = "workflow_runs"

    id = Column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    workflow_id = Column(String, ForeignKey("workflows.id"), nullable=False)
    status = Column(String(50), default="pending")  # pending/running/completed/failed
    input_text = Column(Text, default="")
    output_json = Column(Text, default="{}")
    duration = Column(Float, nullable=True)
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))

    @property
    def output(self) -> dict:
        return json.loads(self.output_json)

    @output.setter
    def output(self, value: dict):
        self.output_json = json.dumps(value, ensure_ascii=False, cls=_RunOutputEncoder)
