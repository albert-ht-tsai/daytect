from datetime import date as date_cls
from datetime import datetime, timezone
from uuid import uuid4

from sqlalchemy import JSON, Column, Date, DateTime, ForeignKey, Integer, String, Text
from sqlalchemy.orm import relationship

from src.core.database import Base


def _new_job_id() -> str:
    return f"sum_{uuid4().hex[:20]}"


class AiHealthSummaryJob(Base):
    __tablename__ = "ai_health_summary_jobs"

    id = Column(Integer, primary_key=True, index=True)
    job_id = Column(String, unique=True, index=True, nullable=False, default=_new_job_id)
    device_id = Column(Integer, ForeignKey("devices.id"), nullable=False, index=True)
    date = Column(Date, nullable=False, index=True)

    status = Column(String, nullable=False, default="queued")
    progress_state = Column(String, nullable=False, default="Queued")
    progress_message = Column(String, nullable=True)

    batch_count = Column(Integer, nullable=False, default=0)
    completed_batch_count = Column(Integer, nullable=False, default=0)

    final_summary_json = Column(JSON, nullable=True)
    error_message = Column(Text, nullable=True)

    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc), nullable=False)
    updated_at = Column(
        DateTime,
        default=lambda: datetime.now(timezone.utc),
        onupdate=lambda: datetime.now(timezone.utc),
        nullable=False,
    )
    completed_at = Column(DateTime, nullable=True)

    device = relationship("Device")
    chunks = relationship("AiHealthSummaryChunk", back_populates="job", cascade="all, delete-orphan")


class AiHealthSummaryChunk(Base):
    __tablename__ = "ai_health_summary_chunks"

    id = Column(Integer, primary_key=True, index=True)
    job_id = Column(Integer, ForeignKey("ai_health_summary_jobs.id"), nullable=False, index=True)
    batch_index = Column(Integer, nullable=False)
    start_time = Column(String, nullable=False)
    end_time = Column(String, nullable=False)

    status = Column(String, nullable=False, default="pending")
    input_json = Column(JSON, nullable=True)
    partial_summary_json = Column(JSON, nullable=True)
    error_message = Column(Text, nullable=True)

    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc), nullable=False)
    updated_at = Column(
        DateTime,
        default=lambda: datetime.now(timezone.utc),
        onupdate=lambda: datetime.now(timezone.utc),
        nullable=False,
    )

    job = relationship("AiHealthSummaryJob", back_populates="chunks")
