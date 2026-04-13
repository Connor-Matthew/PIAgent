from datetime import datetime, timezone
from sqlalchemy import Column, String, Text, Integer, DateTime
from backend.database import Base
import uuid

class KnowledgeBase(Base):
    __tablename__ = "knowledge_bases"

    id = Column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    name = Column(String(255), nullable=False)
    description = Column(Text, default="")
    doc_count = Column(Integer, default=0)
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))
