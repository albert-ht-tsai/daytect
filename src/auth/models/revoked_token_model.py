from datetime import datetime, timezone

from sqlalchemy import Column, DateTime, Integer, String

from src.core.database import Base


class RevokedTokenRecord(Base):
    """A JWT explicitly invalidated via /auth/logout, checked by token_hash so the raw token is
    never stored. `expires_at` mirrors the token's own `exp` claim purely for pruning — once past,
    the token would already fail signature verification on its own, so the row is safe to delete."""

    __tablename__ = "revoked_token_records"

    id = Column(Integer, primary_key=True, index=True)
    token_hash = Column(String(64), unique=True, index=True, nullable=False)
    subject = Column(String(255), nullable=True)
    expires_at = Column(DateTime, nullable=False)
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc), nullable=False)
