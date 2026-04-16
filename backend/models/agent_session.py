import json
import uuid
from datetime import datetime, timezone

from sqlalchemy import Column, DateTime, ForeignKey, String, Text

from backend.database import Base


class AgentSession(Base):
    __tablename__ = "agent_sessions"

    id = Column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    user_goal = Column(Text, nullable=False)
    status = Column(String(32), nullable=False, default="ready")
    turns_json = Column(Text, nullable=False, default="[]")
    answered_dims_json = Column(Text, nullable=False, default="{}")
    events_json = Column(Text, nullable=False, default="[]")
    recipe_json = Column(Text, nullable=True)
    graph_json = Column(Text, nullable=True)
    rationale_text = Column(Text, nullable=True)
    workflow_id = Column(String, ForeignKey("workflows.id"), nullable=True)
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))
    updated_at = Column(
        DateTime,
        default=lambda: datetime.now(timezone.utc),
        onupdate=lambda: datetime.now(timezone.utc),
    )

    @property
    def turns(self) -> list[dict]:
        return json.loads(self.turns_json or "[]")

    @turns.setter
    def turns(self, value: list[dict]):
        self.turns_json = json.dumps(value or [], ensure_ascii=False)

    @property
    def recipe(self) -> dict | None:
        if not self.recipe_json:
            return None
        return json.loads(self.recipe_json)

    @recipe.setter
    def recipe(self, value: dict | None):
        self.recipe_json = (
            json.dumps(value, ensure_ascii=False) if value is not None else None
        )

    @property
    def graph(self) -> dict | None:
        if not self.graph_json:
            return None
        return json.loads(self.graph_json)

    @graph.setter
    def graph(self, value: dict | None):
        self.graph_json = (
            json.dumps(value, ensure_ascii=False) if value is not None else None
        )

    @property
    def answered_dims(self) -> dict:
        return json.loads(self.answered_dims_json or "{}")

    @answered_dims.setter
    def answered_dims(self, value: dict):
        self.answered_dims_json = json.dumps(value or {}, ensure_ascii=False)

    @property
    def events(self) -> list[dict]:
        return json.loads(self.events_json or "[]")

    @events.setter
    def events(self, value: list[dict]):
        self.events_json = json.dumps(value or [], ensure_ascii=False)
