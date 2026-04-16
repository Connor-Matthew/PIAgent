from datetime import datetime, timezone
from sqlalchemy import Column, Integer, String, Text, Boolean, JSON, DateTime

from backend.database import Base


class Provider(Base):
    __tablename__ = "providers"

    id = Column(Integer, primary_key=True)
    type = Column(String(32), nullable=False)
    name = Column(String(64), nullable=False, unique=True)
    base_url = Column(String(256), nullable=True)
    api_key_encrypted = Column(Text, nullable=False)
    enabled = Column(Boolean, default=True, nullable=False)
    category = Column(String(16), default="llm", nullable=False)
    extra_config = Column(JSON, default=dict)
    selected_models = Column(JSON, default=list)
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))
    updated_at = Column(
        DateTime,
        default=lambda: datetime.now(timezone.utc),
        onupdate=lambda: datetime.now(timezone.utc),
    )
