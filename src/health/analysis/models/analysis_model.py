from datetime import datetime, timezone

from sqlalchemy import JSON, Column, Date, DateTime, ForeignKey, Integer, String, UniqueConstraint
from sqlalchemy.orm import relationship

from src.core.database import Base


class Analysis(Base):
    __tablename__ = "analyses"
    __table_args__ = (
        UniqueConstraint("device_id", "range", "start_date", "end_date", name="uq_analyses_device_range_period"),
    )

    id = Column(Integer, primary_key=True, index=True)
    device_id = Column(Integer, ForeignKey("devices.id"), nullable=False, index=True)
    range = Column(String(10), nullable=False)
    start_date = Column(Date, nullable=False, index=True)
    end_date = Column(Date, nullable=False, index=True)
    status = Column(String(20), nullable=False, default="pending")
    content = Column(JSON, nullable=True)
    error_message = Column(String(500), nullable=True)
    generated_at = Column(DateTime, nullable=True)
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc), nullable=False)

    device = relationship("Device")
