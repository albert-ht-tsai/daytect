from datetime import datetime, timezone

from sqlalchemy import Boolean, Column, DateTime, Integer, String

from src.core.database import Base


class DeviceRecord(Base):
    __tablename__ = "device_records"

    id = Column(Integer, primary_key=True, index=True)
    name = Column(String(255), nullable=True)
    mac_address = Column(String(50), unique=True, index=True, nullable=False)
    battery = Column(Integer, nullable=True)
    last_sync = Column(String(19), nullable=True)
    is_connected = Column(Boolean, nullable=False, default=False)
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc), nullable=False)
    updated_at = Column(
        DateTime,
        default=lambda: datetime.now(timezone.utc),
        onupdate=lambda: datetime.now(timezone.utc),
        nullable=False,
    )
