from datetime import datetime, timezone

from sqlalchemy import Column, DateTime, Integer, String, Text, UniqueConstraint

from src.core.database import Base


class AnalysisPicRecord(Base):
    __tablename__ = "analysis_pic_records"
    __table_args__ = (UniqueConstraint("mac_address", "pic_id"),)

    id = Column(Integer, primary_key=True, index=True)
    mac_address = Column(String(50), nullable=False, index=True)
    session_id = Column(String(64), nullable=True, index=True)
    pic_id = Column(String(64), nullable=False, index=True)
    pic_message = Column(Text, nullable=True)
    image_path = Column(String(512), nullable=True)
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc), nullable=False)
    updated_at = Column(
        DateTime,
        default=lambda: datetime.now(timezone.utc),
        onupdate=lambda: datetime.now(timezone.utc),
        nullable=False,
    )
