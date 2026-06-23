from datetime import datetime, timezone

from sqlalchemy import JSON, Column, DateTime, ForeignKey, Integer, String, Text
from sqlalchemy.orm import relationship

from src.core.database import Base


class ReportBatch(Base):
    __tablename__ = "report_batches"

    id = Column(Integer, primary_key=True, index=True)
    task_id = Column(Integer, ForeignKey("report_tasks.id"), nullable=False, index=True)
    batch_index = Column(Integer, nullable=False)
    data_scope = Column(JSON, nullable=True)

    status = Column(String, nullable=False, default="pending")
    estimated_input_tokens = Column(Integer, nullable=False, default=0)
    actual_input_tokens = Column(Integer, nullable=False, default=0)
    actual_output_tokens = Column(Integer, nullable=False, default=0)

    batch_payload = Column(JSON, nullable=True)
    batch_analysis = Column(JSON, nullable=True)
    error_message = Column(Text, nullable=True)
    retry_count = Column(Integer, nullable=False, default=0)

    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc), nullable=False)
    updated_at = Column(
        DateTime,
        default=lambda: datetime.now(timezone.utc),
        onupdate=lambda: datetime.now(timezone.utc),
        nullable=False,
    )
    completed_at = Column(DateTime, nullable=True)

    task = relationship("ReportTask", back_populates="batches")
