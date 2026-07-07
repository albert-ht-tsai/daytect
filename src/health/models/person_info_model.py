from datetime import datetime, timezone

from sqlalchemy import Column, DateTime, Float, Integer, String, Text

from src.core.database import Base


class PersonInfoRecord(Base):
    __tablename__ = "person_info_records"

    id = Column(Integer, primary_key=True, index=True)
    device_id = Column(Integer, unique=True, nullable=False, index=True)
    sex = Column(String(10), nullable=False)
    age = Column(Integer, nullable=False)
    height = Column(Float, nullable=False)
    weight = Column(Float, nullable=False)
    allergy = Column(Text, nullable=True)
    medical_history = Column(Text, nullable=True)
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc), nullable=False)
    updated_at = Column(
        DateTime,
        default=lambda: datetime.now(timezone.utc),
        onupdate=lambda: datetime.now(timezone.utc),
        nullable=False,
    )
