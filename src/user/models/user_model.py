from datetime import datetime, timezone

from sqlalchemy import Boolean, Column, DateTime, Float, ForeignKey, Integer, String, Text
from sqlalchemy.orm import relationship

from src.core.database import Base


class User(Base):
    __tablename__ = "users"

    id = Column(Integer, primary_key=True, index=True)
    email = Column(String(255), unique=True, index=True, nullable=False)
    password = Column(String(255), nullable=False)
    is_active = Column(Boolean, default=True, nullable=False)
    name = Column(String(100), nullable=True)
    region = Column(String(50), nullable=True)
    sex = Column(String(20), nullable=True)
    height = Column(Float, nullable=True)
    height_unit = Column(String(10), nullable=True)
    weight = Column(Float, nullable=True)
    weight_unit = Column(String(10), nullable=True)
    skin_color = Column(String(50), nullable=True)
    age = Column(Integer, nullable=True)
    step_aim = Column(Float, nullable=True)
    step_aim_type = Column(String(10), nullable=True)
    sleep_aim = Column(Float, nullable=True)
    sleep_aim_type = Column(String(10), nullable=True)
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc), nullable=False)

    tokens = relationship("UserToken", back_populates="user")


class UserToken(Base):
    __tablename__ = "user_tokens"

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False, index=True)
    access_token = Column(Text, nullable=False)
    refresh_token = Column(Text, nullable=False)
    access_token_expire = Column(DateTime, nullable=False)
    refresh_token_expire = Column(DateTime, nullable=False)
    revoked = Column(Boolean, default=False, nullable=False)
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc), nullable=False)

    user = relationship("User", back_populates="tokens")
