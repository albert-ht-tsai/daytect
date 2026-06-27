from datetime import datetime, timezone

from sqlalchemy import Column, DateTime, Float, ForeignKey, Integer, String, UniqueConstraint
from sqlalchemy.orm import relationship

from src.core.database import Base


class RawActivity(Base):
    __tablename__ = "raw_activity_records"
    __table_args__ = (UniqueConstraint("user_id", "mac_address", "device_time", name="uq_raw_activity"),)

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False, index=True)
    mac_address = Column(String(17), nullable=False)
    device_time = Column(DateTime, nullable=False, index=True)
    step_value = Column(Integer, nullable=True)
    sport_value = Column(Integer, nullable=True)
    calories = Column(Float, nullable=True)
    distance_km = Column(Float, nullable=True)
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc), nullable=False)
    updated_at = Column(
        DateTime,
        default=lambda: datetime.now(timezone.utc),
        onupdate=lambda: datetime.now(timezone.utc),
        nullable=False,
    )

    user = relationship("User")
