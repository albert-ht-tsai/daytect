from datetime import datetime, timezone

from sqlalchemy import Boolean, Column, DateTime, Float, ForeignKey, Integer, String, UniqueConstraint
from sqlalchemy.orm import relationship

from src.core.database import Base


class Device(Base):
    __tablename__ = "devices"
    __table_args__ = (UniqueConstraint("user_id", "mac_address", name="uq_devices_user_mac"),)

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False, index=True)
    mac_address = Column(String(17), nullable=False)
    name = Column(String(100), nullable=True)
    avatar = Column(String(255), nullable=True)
    group = Column(String(50), nullable=False, default="my_devices")
    is_share = Column(Boolean, default=False, nullable=False)
    qrcode = Column(String(64), nullable=False)
    battery = Column(Float, default=0, nullable=False)
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc), nullable=False)

    user = relationship("User")
