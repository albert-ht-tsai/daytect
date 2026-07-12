from datetime import datetime, timezone

from sqlalchemy import Column, DateTime, Integer, String, Text
from sqlalchemy.types import JSON

from src.core.database import Base


class HealthSummaryRecord(Base):
    """One health-summary turn: a user question answered against a prior response already
    stored on OpenAI's side (either a /data_summary call or an earlier /health_summary turn in
    the same follow-up chain). Append-only, like AnalysisRecord — a session's follow-up
    questions each get their own row rather than overwriting the last one.
    """

    __tablename__ = "health_summary_records"

    id = Column(Integer, primary_key=True, index=True)
    mac_address = Column(String(50), nullable=False, index=True)
    user_input = Column(Text, nullable=False)
    # The response id this call was chained from (a /data_summary responseId, or an earlier
    # /health_summary responseId for a follow-up question).
    data_summary_response_id = Column(String(128), nullable=False, index=True)
    # This turn's own OpenAI Responses API id, returned to the frontend so a further follow-up
    # question can chain from it instead of the original data-summary response.
    health_summary_response_id = Column(String(128), nullable=True, index=True)
    # Id of the AnalysisPicRecord audit row for an image attached to this turn, if any
    # (see analysis_pic_model.py). Null when no image was uploaded.
    pic_id = Column(String(64), nullable=True, index=True)
    health_summary = Column(JSON, nullable=True)
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc), nullable=False)
    updated_at = Column(
        DateTime,
        default=lambda: datetime.now(timezone.utc),
        onupdate=lambda: datetime.now(timezone.utc),
        nullable=False,
    )
