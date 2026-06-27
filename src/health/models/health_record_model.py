from datetime import datetime, timezone

from sqlalchemy import JSON, Column, Date, DateTime, ForeignKey, Integer, String, UniqueConstraint
from sqlalchemy.orm import relationship

from src.core.database import Base


class HealthRecord(Base):
    __tablename__ = "health_records"
    __table_args__ = (UniqueConstraint("user_id", "date", name="uq_health_records_user_date"),)

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False, index=True)
    date = Column(Date, nullable=False, index=True)
    source_mac_address = Column(String(17), nullable=True)
    sleep = Column(JSON, nullable=True)
    heart_rate = Column(JSON, nullable=True)
    blood_pressure = Column(JSON, nullable=True)
    blood_oxygen = Column(JSON, nullable=True)
    body_temperature = Column(JSON, nullable=True)
    skin_temperature = Column(JSON, nullable=True)
    activity = Column(JSON, nullable=True)
    respiratory_rate = Column(JSON, nullable=True)
    apnea = Column(JSON, nullable=True)
    cardiac_load = Column(JSON, nullable=True)
    sport_status = Column(JSON, nullable=True)
    blood_glucose = Column(JSON, nullable=True)
    blood_component = Column(JSON, nullable=True)
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc), nullable=False)
    updated_at = Column(
        DateTime,
        default=lambda: datetime.now(timezone.utc),
        onupdate=lambda: datetime.now(timezone.utc),
        nullable=False,
    )

    user = relationship("User")
