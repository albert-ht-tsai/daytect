from datetime import datetime, timezone

from sqlalchemy import Column, DateTime, Float, Integer, String, Text, UniqueConstraint

from src.core.database import Base


class DailyHealthSummaryRecord(Base):
    __tablename__ = "daily_health_summaries"
    __table_args__ = (UniqueConstraint("device_id", "date"),)

    id = Column(Integer, primary_key=True, index=True)
    device_id = Column(Integer, nullable=False, index=True)
    date = Column(String(10), nullable=False)

    sleep_score = Column(Float, nullable=True)
    sleep_summary = Column(Text, nullable=True)
    sleep_suggestion = Column(Text, nullable=True)

    activity_score = Column(Float, nullable=True)
    activity_summary = Column(Text, nullable=True)
    activity_suggestion = Column(Text, nullable=True)

    health_score = Column(Float, nullable=True)
    health_summary = Column(Text, nullable=True)
    health_suggestion = Column(Text, nullable=True)

    overall_score = Column(Float, nullable=True)
    overall_summary = Column(Text, nullable=True)
    overall_suggestion = Column(Text, nullable=True)

    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc), nullable=False)
    updated_at = Column(
        DateTime,
        default=lambda: datetime.now(timezone.utc),
        onupdate=lambda: datetime.now(timezone.utc),
        nullable=False,
    )
