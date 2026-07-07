from datetime import datetime, timezone

from sqlalchemy import Column, DateTime, Float, Integer, String, Text, UniqueConstraint

from src.core.database import Base


class HealthInsightRecord(Base):
    __tablename__ = "health_insight_records"
    __table_args__ = (UniqueConstraint("device_id", "session"),)

    id = Column(Integer, primary_key=True, index=True)
    device_id = Column(Integer, nullable=False, index=True)
    session = Column(Integer, nullable=False)
    start_date = Column(String(10), nullable=False)
    end_date = Column(String(10), nullable=False)

    health_score = Column(Float, nullable=True)
    health_score_label = Column(String(10), nullable=True)
    health_score_threshold = Column(String(50), nullable=True)

    heart_rate = Column(Float, nullable=True)
    heart_rate_label = Column(String(10), nullable=True)
    heart_rate_threshold = Column(String(50), nullable=True)

    blood_pressure = Column(String(20), nullable=True)
    blood_pressure_label = Column(String(10), nullable=True)
    blood_pressure_threshold = Column(String(50), nullable=True)

    blood_oxygen = Column(Float, nullable=True)
    blood_oxygen_label = Column(String(10), nullable=True)
    blood_oxygen_threshold = Column(String(50), nullable=True)

    body_temperature = Column(Float, nullable=True)
    body_temperature_label = Column(String(10), nullable=True)
    body_temperature_threshold = Column(String(50), nullable=True)

    hrv = Column(Float, nullable=True)
    hrv_label = Column(String(10), nullable=True)
    hrv_threshold = Column(String(50), nullable=True)

    res_rate = Column(Float, nullable=True)
    res_rate_label = Column(String(10), nullable=True)
    res_rate_threshold = Column(String(50), nullable=True)

    pressure = Column(Float, nullable=True)
    pressure_label = Column(String(10), nullable=True)
    pressure_threshold = Column(String(50), nullable=True)

    sleep_quality = Column(Float, nullable=True)
    sleep_quality_label = Column(String(10), nullable=True)
    sleep_quality_threshold = Column(String(50), nullable=True)

    sleep_duration = Column(Float, nullable=True)
    sleep_duration_label = Column(String(10), nullable=True)
    sleep_duration_threshold = Column(String(50), nullable=True)

    activity_steps = Column(Float, nullable=True)
    activity_steps_label = Column(String(10), nullable=True)
    activity_steps_threshold = Column(String(50), nullable=True)

    sleep_summary = Column(Text, nullable=True)
    activity_summary = Column(Text, nullable=True)
    health_summary = Column(Text, nullable=True)

    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc), nullable=False)
    updated_at = Column(
        DateTime,
        default=lambda: datetime.now(timezone.utc),
        onupdate=lambda: datetime.now(timezone.utc),
        nullable=False,
    )
