from datetime import datetime, timezone

from sqlalchemy import Column, DateTime, Integer, String, UniqueConstraint

from src.core.database import Base


class SleepRecord(Base):
    __tablename__ = "sleep_records"
    __table_args__ = (UniqueConstraint("device_id", "date"),)

    id = Column(Integer, primary_key=True, index=True)
    device_id = Column(Integer, nullable=False, index=True)
    date = Column(String(10), nullable=False)
    sleep_quality = Column(Integer, nullable=True)
    wake_count = Column(Integer, nullable=True)
    deep_sleep_time = Column(Integer, nullable=True)
    low_sleep_time = Column(Integer, nullable=True)
    all_sleep_time = Column(Integer, nullable=True)
    sleep_line = Column(String(1024), nullable=True)
    sleep_down_hour = Column(Integer, nullable=True)
    sleep_down_minute = Column(Integer, nullable=True)
    sleep_up_hour = Column(Integer, nullable=True)
    sleep_up_minute = Column(Integer, nullable=True)
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc), nullable=False)
    updated_at = Column(
        DateTime,
        default=lambda: datetime.now(timezone.utc),
        onupdate=lambda: datetime.now(timezone.utc),
        nullable=False,
    )
