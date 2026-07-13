from datetime import datetime, timezone

from sqlalchemy import Boolean, Column, DateTime, Integer, String, UniqueConstraint
from sqlalchemy.types import JSON

from src.core.database import Base


class TrendSummaryRecord(Base):
    """One 健康趨勢摘要 row per (mac_address, end_date) (assistant stage 2). Chained via
    previous_response_id from an /assistant/profile call (or an earlier /assistant/trend
    follow-up), so the AI already has this user's profile/level in context server-side."""

    __tablename__ = "assistant_trend_summary_records"
    __table_args__ = (UniqueConstraint("mac_address", "end_date"),)

    id = Column(Integer, primary_key=True, index=True)
    mac_address = Column(String(50), nullable=False, index=True)
    start_date = Column(String(10), nullable=False)
    end_date = Column(String(10), nullable=False)
    # Raw system-computed avg/min/max per sleep/health/activity metric (see
    # trend_summary_service._aggregate_*_trend) — never invented by the AI.
    trend_data = Column(JSON, nullable=True)
    # Full AI response: levelConsistent/reassessedLevel/reassessedStandard plus the per-metric
    # value/label/suggestion breakdown for sleep/health/activity.
    ai_response = Column(JSON, nullable=True)
    level_consistent = Column(Boolean, nullable=True)
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
