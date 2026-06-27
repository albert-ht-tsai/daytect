from datetime import datetime, timezone

from sqlalchemy import JSON, Column, DateTime, Float, ForeignKey, Integer, String, UniqueConstraint
from sqlalchemy.orm import relationship

from src.core.database import Base


class RawHealthRecord(Base):
    __tablename__ = "raw_health_records"
    __table_args__ = (UniqueConstraint("user_id", "mac_address", "device_time", name="uq_raw_health_records"),)

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False, index=True)
    mac_address = Column(String(17), nullable=False)
    device_time = Column(DateTime, nullable=False, index=True)
    heart_rate = Column(JSON, nullable=True)
    blood_pressure = Column(JSON, nullable=True)
    blood_oxygen = Column(JSON, nullable=True)
    respiratory_rate = Column(JSON, nullable=True)
    body_temperature = Column(JSON, nullable=True)
    sleep_state = Column(JSON, nullable=True)
    apnea = Column(JSON, nullable=True)
    cardiac_load = Column(JSON, nullable=True)
    blood_glucose = Column(Float, nullable=True)
    blood_component = Column(JSON, nullable=True)
    sport_status = Column(JSON, nullable=True)
    met = Column(Float, nullable=True)
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc), nullable=False)
    updated_at = Column(
        DateTime,
        default=lambda: datetime.now(timezone.utc),
        onupdate=lambda: datetime.now(timezone.utc),
        nullable=False,
    )

    user = relationship("User")
