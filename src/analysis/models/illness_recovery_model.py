from datetime import datetime, timezone

from sqlalchemy import Column, DateTime, Integer, String, Text, UniqueConstraint
from sqlalchemy.types import JSON

from src.core.database import Base


class IllnessRecoveryRecord(Base):
    __tablename__ = "illness_recovery_records"
    __table_args__ = (UniqueConstraint("device_id", "date"),)

    id = Column(Integer, primary_key=True, index=True)
    device_id = Column(Integer, nullable=False, index=True)
    date = Column(String(10), nullable=False)

    illness_level = Column(String(20), nullable=False)
    recovery_status = Column(String(20), nullable=False)
    trend = Column(String(20), nullable=False)
    joint_status = Column(String(30), nullable=False)

    main_findings = Column(JSON, nullable=True)
    alternative_explanation = Column(Text, nullable=True)
    summary = Column(Text, nullable=True)

    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc), nullable=False)
    updated_at = Column(
        DateTime,
        default=lambda: datetime.now(timezone.utc),
        onupdate=lambda: datetime.now(timezone.utc),
        nullable=False,
    )
