from datetime import datetime, timezone

from sqlalchemy import Column, DateTime, Integer, String, UniqueConstraint
from sqlalchemy.types import JSON

from src.core.database import Base


class DataSummaryRecord(Base):
    """One saved 7-day data-summary report per (mac_address, report_date). Re-generating for
    the same mac_address + report_date overwrites this row rather than accumulating history —
    see data_summary_service.get_or_generate_summary for the reuse-vs-regenerate decision.
    """

    __tablename__ = "data_summary_records"
    __table_args__ = (UniqueConstraint("mac_address", "report_date"),)

    id = Column(Integer, primary_key=True, index=True)
    mac_address = Column(String(50), nullable=False, index=True)
    report_date = Column(String(10), nullable=False, index=True)
    # Stored with timezone=True (unlike this codebase's other DateTime columns, which are always
    # implicitly UTC audit timestamps) because the API response must round-trip the actual
    # +08:00 report boundary rather than a UTC instant — see data_summary_service.REPORT_TZ.
    start_time = Column(DateTime(timezone=True), nullable=False)
    end_time = Column(DateTime(timezone=True), nullable=False)
    sleep_summary = Column(JSON, nullable=True)
    health_summary = Column(JSON, nullable=True)
    metric_status = Column(JSON, nullable=True)
    ai_response = Column(JSON, nullable=True)
    # OpenAI Responses API id for this report's generation call. Returned to the frontend as
    # `responseId` so it can be passed as `previousResponseId` to /health_summary, which relies
    # on OpenAI already having this macAddress + 7-day data in context server-side rather than
    # re-querying the database itself.
    response_id = Column(String(128), nullable=True, index=True)
    # Id of the AnalysisPicRecord audit row for an image attached to this report's generation
    # call, if any (see analysis_pic_model.py). Null when no image was uploaded.
    pic_id = Column(String(64), nullable=True, index=True)
    prompt_version = Column(String(32), nullable=False)
    # Latest updated_at among the SleepRecord/HealthRecord rows this summary was computed from;
    # compared against fresh source rows on the next request to decide whether the saved summary
    # is still valid or must be regenerated, without diffing full row contents every time.
    source_updated_at = Column(DateTime, nullable=True)
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc), nullable=False)
    updated_at = Column(
        DateTime,
        default=lambda: datetime.now(timezone.utc),
        onupdate=lambda: datetime.now(timezone.utc),
        nullable=False,
    )
