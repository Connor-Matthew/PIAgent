import json
from datetime import datetime, timezone
from sqlalchemy import Column, String, Text, DateTime
from backend.database import Base
import uuid

class Workflow(Base):
    __tablename__ = "workflows"

    id = Column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    name = Column(String(255), nullable=False)
    description = Column(Text, default="")
    graph_json = Column(Text, nullable=False)  # {nodes: [...], edges: [...]}
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))
    updated_at = Column(DateTime, default=lambda: datetime.now(timezone.utc), onupdate=lambda: datetime.now(timezone.utc))

    @property
    def graph(self) -> dict:
        return json.loads(self.graph_json)

    @graph.setter
    def graph(self, value: dict):
        self.graph_json = json.dumps(value)
