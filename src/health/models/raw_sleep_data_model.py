from datetime import datetime, timezone

from sqlalchemy import Column, Date, DateTime, ForeignKey, Integer, String, UniqueConstraint
from sqlalchemy.orm import relationship

from src.core.database import Base


class RawSleepData(Base):
    __tablename__ = "raw_sleep_data"
    __table_args__ = (UniqueConstraint("user_id", "mac_address", "sleep_date", name="uq_raw_sleep_data"),)

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False, index=True)
    mac_address = Column(String(17), nullable=False)
    sleep_date = Column(Date, nullable=False, index=True)
    cali_flag = Column(Integer, nullable=True)
    sleep_quality = Column(Integer, nullable=True)
    wake_count = Column(Integer, nullable=True)
    deep_sleep_minutes = Column(Integer, nullable=True)
    light_sleep_minutes = Column(Integer, nullable=True)
    total_sleep_minutes = Column(Integer, nullable=True)
    sleep_start = Column(String(50), nullable=True)
    sleep_end = Column(String(50), nullable=True)
    sleep_line = Column(String(1000), nullable=True)
    sleep_line_type = Column(String(50), nullable=True)
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc), nullable=False)
    updated_at = Column(
        DateTime,
        default=lambda: datetime.now(timezone.utc),
        onupdate=lambda: datetime.now(timezone.utc),
        nullable=False,
    )

    user = relationship("User")
