from datetime import datetime, timezone

from sqlalchemy import Column, DateTime, Integer, String

from src.core.database import Base


class VerificationCode(Base):
    __tablename__ = "verification_codes"

    id = Column(Integer, primary_key=True, index=True)
    email = Column(String(255), unique=True, index=True, nullable=False)
    code = Column(String(10), nullable=False)
    expire_at = Column(DateTime, nullable=False)
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc), nullable=False)
