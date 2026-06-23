from datetime import datetime, timezone

from sqlalchemy import JSON, Column, Date, DateTime, ForeignKey, Integer, String
from sqlalchemy.orm import relationship

from src.core.database import Base


class ReportResult(Base):
    __tablename__ = "report_results"

    id = Column(Integer, primary_key=True, index=True)
    report_task_id = Column(String, nullable=False, index=True)
    device_id = Column(Integer, ForeignKey("devices.id"), nullable=False, index=True)
    report_type = Column(String, nullable=False)
    date = Column(Date, nullable=False)

    date_range = Column(JSON, nullable=False)
    overall_status = Column(String, nullable=False)
    summary = Column(JSON, nullable=False)
    ai_report = Column(JSON, nullable=False)
    token_usage = Column(JSON, nullable=False)

    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc), nullable=False)
    completed_at = Column(DateTime, nullable=True)

    device = relationship("Device")
