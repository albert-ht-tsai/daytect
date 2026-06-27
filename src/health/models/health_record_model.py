from datetime import datetime, timezone

from sqlalchemy import JSON, Column, Date, DateTime, Float, ForeignKey, Integer, UniqueConstraint
from sqlalchemy.orm import relationship

from src.core.database import Base


class HealthRecord(Base):
    __tablename__ = "health_records"
    __table_args__ = (UniqueConstraint("user_id", "datetime", name="uq_health_records_user_datetime"),)

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False, index=True)
    date = Column(Date, nullable=False, index=True)
    datetime = Column(DateTime, nullable=False, index=True)
    heart_rate = Column(Float, nullable=True)
    blood_oxygen = Column(Float, nullable=True)
    respiratory_rate = Column(Float, nullable=True)
    sleep_state = Column(Integer, nullable=True)
    apnea_result = Column(Integer, nullable=True)
    hypoxia_time = Column(Integer, nullable=True)
    cardiac_load = Column(Float, nullable=True)
    is_hypoxia = Column(Integer, nullable=True)
    correct = Column(Integer, nullable=True)
    blood_glucose = Column(Float, nullable=True)
    sport_status = Column(Integer, nullable=True)
    blood_component = Column(JSON, nullable=True)
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc), nullable=False)
    updated_at = Column(
        DateTime,
        default=lambda: datetime.now(timezone.utc),
        onupdate=lambda: datetime.now(timezone.utc),
        nullable=False,
    )

    user = relationship("User")
