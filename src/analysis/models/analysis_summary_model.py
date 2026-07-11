from datetime import datetime, timezone

from sqlalchemy import Column, DateTime, Integer, String, Text, UniqueConstraint

from src.core.database import Base


class AnalysisSummaryRecord(Base):
    """Compacted key-point digest of a chat session's recent AnalysisRecord turns.

    One row per (mac_address, session_id): re-compacting the same session overwrites the
    previous digest rather than accumulating history rows.
    """

    __tablename__ = "analysis_summary_records"
    __table_args__ = (UniqueConstraint("mac_address", "session_id"),)

    id = Column(Integer, primary_key=True, index=True)
    mac_address = Column(String(50), nullable=False, index=True)
    session_id = Column(String(64), nullable=False, index=True)
    summary = Column(Text, nullable=False)
    source_count = Column(Integer, nullable=False)
    start_record_datetime = Column(DateTime, nullable=True)
    end_record_datetime = Column(DateTime, nullable=True)
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc), nullable=False)
    updated_at = Column(
        DateTime,
        default=lambda: datetime.now(timezone.utc),
        onupdate=lambda: datetime.now(timezone.utc),
        nullable=False,
    )
