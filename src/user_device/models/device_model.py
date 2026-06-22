from datetime import datetime, timezone

from sqlalchemy import Boolean, Column, DateTime, ForeignKey, Integer, String
from sqlalchemy.orm import relationship

from src.core.database import Base


class Device(Base):
    __tablename__ = "devices"

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False, index=True)
    mac_address = Column(String(50), unique=True, nullable=False, index=True)
    name = Column(String(100), nullable=False)
    device_type = Column(String(50), nullable=False, default="wearable")
    group = Column(String(20), nullable=False, default="my_devices")
    is_share = Column(Boolean, nullable=False, default=False)
    bluetooth_status = Column(String(20), nullable=False, default="disconnected")
    sync_status = Column(String(20), nullable=False, default="not_synced")
    battery = Column(Integer, nullable=True)
    last_sync_at = Column(DateTime, nullable=True)
    avatar = Column(String(255), nullable=True)
    qrcode = Column(String(255), nullable=False)
    illustration_key = Column(String(50), nullable=False, default="daytect_band_default")
    alert_muted_until = Column(DateTime, nullable=True)
    alert_remind_later_minutes = Column(Integer, nullable=False, default=5)
    alert_last_triggered_at = Column(DateTime, nullable=True)
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc), nullable=False)

    user = relationship("User")
