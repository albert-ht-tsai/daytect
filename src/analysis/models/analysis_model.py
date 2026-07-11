from datetime import datetime, timezone

from sqlalchemy import Column, DateTime, Integer, String, Text, UniqueConstraint

from src.core.database import Base


class AnalysisRecord(Base):
    __tablename__ = "analysis_records"
    __table_args__ = (UniqueConstraint("mac_address", "record_datetime"),)

    id = Column(Integer, primary_key=True, index=True)
    mac_address = Column(String(50), nullable=False, index=True)
    session_id = Column(String(64), nullable=True, index=True)
    record_datetime = Column(DateTime, nullable=False)
    user_question = Column(Text, nullable=True)
    system_answer = Column(Text, nullable=True)
    pic_id = Column(String(64), nullable=True, index=True)
    # OpenAI Responses API id for this turn's reply, passed back as previous_response_id on the
    # session's next turn so OpenAI can resume the conversation server-side instead of this
    # service replaying conversationHistory into the prompt. Null for turns recorded before this
    # column existed, and for the out-of-scope short-circuit / regenerated-summary error path.
    openai_response_id = Column(String(128), nullable=True, index=True)
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc), nullable=False)
    updated_at = Column(
        DateTime,
        default=lambda: datetime.now(timezone.utc),
        onupdate=lambda: datetime.now(timezone.utc),
        nullable=False,
    )
