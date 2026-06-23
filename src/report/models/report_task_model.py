from datetime import datetime, timezone
from uuid import uuid4

from sqlalchemy import Column, Date, DateTime, ForeignKey, Integer, String, Text, UniqueConstraint
from sqlalchemy.orm import relationship

from src.core.database import Base


def _new_report_task_id() -> str:
    return f"rpt_{uuid4().hex[:20]}"


class ReportTask(Base):
    __tablename__ = "report_tasks"
    __table_args__ = (UniqueConstraint("device_id", "report_type", "date", name="uq_report_tasks_device_type_date"),)

    id = Column(Integer, primary_key=True, index=True)
    report_task_id = Column(String, unique=True, index=True, nullable=False, default=_new_report_task_id)
    device_id = Column(Integer, ForeignKey("devices.id"), nullable=False, index=True)
    report_type = Column(String, nullable=False)
    date = Column(Date, nullable=False)
    language = Column(String, nullable=False, default="en")

    status = Column(String, nullable=False, default="queued")
    progress_percentage = Column(Integer, nullable=False, default=0)
    current_step = Column(String, nullable=True)
    progress_message = Column(String, nullable=True)

    total_batches = Column(Integer, nullable=False, default=0)
    completed_batches = Column(Integer, nullable=False, default=0)
    processing_batches = Column(Integer, nullable=False, default=0)
    pending_batches = Column(Integer, nullable=False, default=0)
    failed_batches = Column(Integer, nullable=False, default=0)

    estimated_total_input_tokens = Column(Integer, nullable=False, default=0)
    actual_total_input_tokens = Column(Integer, nullable=False, default=0)
    actual_total_output_tokens = Column(Integer, nullable=False, default=0)

    failed_step = Column(String, nullable=True)
    error_code = Column(String, nullable=True)
    error_message = Column(Text, nullable=True)

    result_id = Column(Integer, ForeignKey("report_results.id"), nullable=True)

    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc), nullable=False)
    updated_at = Column(
        DateTime,
        default=lambda: datetime.now(timezone.utc),
        onupdate=lambda: datetime.now(timezone.utc),
        nullable=False,
    )
    completed_at = Column(DateTime, nullable=True)

    device = relationship("Device")
    result = relationship("ReportResult", foreign_keys=[result_id])
    batches = relationship("ReportBatch", back_populates="task", cascade="all, delete-orphan")
