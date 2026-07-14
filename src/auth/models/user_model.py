from datetime import datetime, timezone

from sqlalchemy import Boolean, Column, DateTime, Integer, String

from src.core.database import Base


class UserRecord(Base):
    __tablename__ = "user_records"

    id = Column(Integer, primary_key=True, index=True)
    email = Column(String(255), unique=True, index=True, nullable=False)
    password_hash = Column(String(255), nullable=False)
    is_verified = Column(Boolean, nullable=False, default=False)
    # Tokens with an `iat` before this cutoff are treated as revoked (see
    # auth_service.is_token_revoked) — set on a successful password reset so every
    # previously-issued access token is invalidated at once, without tracking them individually.
    tokens_invalidated_at = Column(DateTime, nullable=True)
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc), nullable=False)
    updated_at = Column(
        DateTime,
        default=lambda: datetime.now(timezone.utc),
        onupdate=lambda: datetime.now(timezone.utc),
        nullable=False,
    )
