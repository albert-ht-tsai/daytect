from datetime import datetime, timezone

from sqlalchemy import Column, Date, DateTime, Float, ForeignKey, Integer, UniqueConstraint
from sqlalchemy.orm import relationship

from src.core.database import Base


class ActivityRecord(Base):
    __tablename__ = "activity_records"
    __table_args__ = (UniqueConstraint("user_id", "datetime", name="uq_activity_records_user_datetime"),)

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False, index=True)
    date = Column(Date, nullable=False, index=True)
    datetime = Column(DateTime, nullable=False, index=True)
    sport_value = Column(Float, nullable=True)
    step_value = Column(Integer, nullable=True)
    wear = Column(Integer, nullable=True)
    cal_value = Column(Float, nullable=True)
    dis_value = Column(Float, nullable=True)
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc), nullable=False)
    updated_at = Column(
        DateTime,
        default=lambda: datetime.now(timezone.utc),
        onupdate=lambda: datetime.now(timezone.utc),
        nullable=False,
    )

    user = relationship("User")
