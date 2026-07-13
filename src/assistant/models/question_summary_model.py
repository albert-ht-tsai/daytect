from datetime import datetime, timezone

from sqlalchemy import Column, DateTime, Float, Integer, String, Text
from sqlalchemy.types import JSON

from src.core.database import Base


class QuestionSummaryRecord(Base):
    """One 用戶問題分析 turn (assistant stage 3). Append-only, like AnalysisRecord /
    HealthSummaryRecord — a session's follow-up questions each get their own row rather than
    overwriting the last one. Chained via previous_response_id from an /assistant/trend call
    (or an earlier /assistant/question follow-up)."""

    __tablename__ = "assistant_question_summary_records"

    id = Column(Integer, primary_key=True, index=True)
    mac_address = Column(String(50), nullable=False, index=True)
    user_question = Column(Text, nullable=False)
    category = Column(String(16), nullable=True)
    confidence = Column(Float, nullable=True)
    # {"response": ..., "benefits": [...]} — see question_summary_service.
    ai_response = Column(JSON, nullable=True)
    image_path = Column(String(512), nullable=True)
    previous_response_id = Column(String(128), nullable=False, index=True)
    response_id = Column(String(128), nullable=True, index=True)
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc), nullable=False)
    updated_at = Column(
        DateTime,
        default=lambda: datetime.now(timezone.utc),
        onupdate=lambda: datetime.now(timezone.utc),
        nullable=False,
    )
