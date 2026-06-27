from datetime import datetime, timezone

from sqlalchemy import Column, Date, DateTime, ForeignKey, Integer, String, Text, UniqueConstraint
from sqlalchemy.orm import relationship

from src.core.database import Base


class SleepRecord(Base):
    __tablename__ = "sleep_records"
    __table_args__ = (UniqueConstraint("user_id", "date", name="uq_sleep_records_user_date"),)

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False, index=True)
    date = Column(Date, nullable=False, index=True)
    sleep_quality = Column(Integer, nullable=True)
    wake_count = Column(Integer, nullable=True)
    deep_sleep_time = Column(Integer, nullable=True)
    low_sleep_time = Column(Integer, nullable=True)
    all_sleep_time = Column(Integer, nullable=True)
    sleep_down = Column(String(50), nullable=True)
    sleep_up = Column(String(50), nullable=True)
    sleep_line = Column(Text, nullable=True)
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc), nullable=False)
    updated_at = Column(
        DateTime,
        default=lambda: datetime.now(timezone.utc),
        onupdate=lambda: datetime.now(timezone.utc),
        nullable=False,
    )

    user = relationship("User")
