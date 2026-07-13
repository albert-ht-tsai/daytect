from datetime import datetime, timezone

from sqlalchemy import Column, DateTime, Float, Integer, String, Text

from src.core.database import Base


class ProfileSummaryRecord(Base):
    """One 身體特徵摘要 row per mac_address (assistant stage 1). Re-generating overwrites this
    row rather than accumulating history, since it always reflects the device's current
    PersonInfoRecord rather than a point-in-time snapshot worth keeping history of."""

    __tablename__ = "assistant_profile_summary_records"

    id = Column(Integer, primary_key=True, index=True)
    mac_address = Column(String(50), nullable=False, unique=True, index=True)
    sex = Column(String(10), nullable=False)
    age = Column(Integer, nullable=False)
    height = Column(Float, nullable=False)
    weight = Column(Float, nullable=False)
    allergy = Column(Text, nullable=True)
    medical_history = Column(Text, nullable=True)
    # Deterministically computed by the backend (see profile_summary_service._determine_level),
    # never decided by the AI — level: normal|low|attention, level_label: 正常|偏低|特別注意,
    # standard: 成人健康標準|老人健康標準|看護級健康標準.
    level = Column(String(16), nullable=False)
    level_label = Column(String(16), nullable=False)
    standard = Column(String(32), nullable=False)
    summary = Column(Text, nullable=False)
    image_path = Column(String(512), nullable=True)
    # This turn's OpenAI Responses API id, returned to the frontend as responseId so
    # /assistant/trend can chain from it via previous_response_id.
    response_id = Column(String(128), nullable=True, index=True)
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc), nullable=False)
    updated_at = Column(
        DateTime,
        default=lambda: datetime.now(timezone.utc),
        onupdate=lambda: datetime.now(timezone.utc),
        nullable=False,
    )
