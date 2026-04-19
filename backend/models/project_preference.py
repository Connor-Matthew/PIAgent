from datetime import datetime, timezone

from sqlalchemy import Column, DateTime, Integer, String, Text

from backend.database import Base


class ProjectPreference(Base):
    __tablename__ = "project_preferences"

    key = Column(String(32), primary_key=True, default="default")
    preferred_llm_provider_id = Column(Integer, nullable=True)
    preferred_tts_provider_id = Column(Integer, nullable=True)
    preferred_tts_voice_id = Column(String(64), nullable=True)
    preferred_knowledge_base_id = Column(String(64), nullable=True)
    graph_style = Column(String(32), nullable=True)
    updated_at = Column(
        DateTime,
        default=lambda: datetime.now(timezone.utc),
        onupdate=lambda: datetime.now(timezone.utc),
    )
