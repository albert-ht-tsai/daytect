from datetime import datetime, timezone

from sqlalchemy import Boolean, Column, DateTime, Integer, String, Text
from sqlalchemy.types import JSON

from src.core.database import Base


class HealthReportRecord(Base):
    """One health-report generation job. Created with status="queued" by POST /health-reports and
    then advanced in the background (see health_report_service.run_generation) through
    "processing" to a terminal "completed"/"failed" state. The two GET endpoints just read this
    row — GET .../status projects the status columns, GET .../{report_id} returns `payload` once
    completed."""

    __tablename__ = "health_report_records"

    id = Column(Integer, primary_key=True, index=True)
    report_id = Column(String(40), unique=True, index=True, nullable=False)
    user_id = Column(Integer, nullable=False, index=True)
    device_id = Column(Integer, nullable=True, index=True)

    report_type = Column(String(50), nullable=False)
    language = Column(String(8), nullable=False)
    include_ai_analysis = Column(Boolean, nullable=False, default=True)

    status = Column(String(16), nullable=False, default="queued")
    stage = Column(String(32), nullable=True)
    progress = Column(Integer, nullable=False, default=0)

    period_start = Column(String(10), nullable=False)
    period_end = Column(String(10), nullable=False)
    comparison_start = Column(String(10), nullable=False)
    comparison_end = Column(String(10), nullable=False)

    # Full assembled report body (data_quality/overall/priority_items/category_summary/
    # sleep_summary/health_summary/activity_summary/ai_analysis) once status="completed".
    payload = Column(JSON, nullable=True)

    error_code = Column(String(64), nullable=True)
    error_message = Column(Text, nullable=True)

    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc), nullable=False)
    updated_at = Column(
        DateTime,
        default=lambda: datetime.now(timezone.utc),
        onupdate=lambda: datetime.now(timezone.utc),
        nullable=False,
    )
    completed_at = Column(DateTime, nullable=True)
