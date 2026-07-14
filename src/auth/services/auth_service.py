import random
from datetime import datetime, timedelta, timezone

from jose import JWTError
from sqlalchemy.orm import Session

from src.auth.models.revoked_token_model import RevokedTokenRecord
from src.auth.models.user_model import UserRecord
from src.auth.models.verification_code_model import VerificationCodeRecord
from src.auth.schemas.auth_schema import (
    LoginRequest,
    LogoutRequest,
    RegisterRequest,
    SendVerificationRequest,
    TokenResponse,
)
from src.auth.services.errors import AuthError
from src.core.email import send_email
from src.core.security import (
    create_access_token,
    decode_token,
    get_password_hash,
    hash_token,
    verify_password,
)

VERIFICATION_CODE_TTL_MINUTES = 10


def send_verification_code(db: Session, body: SendVerificationRequest) -> None:
    code = f"{random.randint(0, 999999):06d}"
    expires_at = datetime.utcnow() + timedelta(minutes=VERIFICATION_CODE_TTL_MINUTES)

    db.add(VerificationCodeRecord(email=body.email, code=code, expires_at=expires_at))
    db.commit()

    send_email(
        to=body.email,
        subject="Your verification code",
        body=f"Your verification code is {code}. It expires in {VERIFICATION_CODE_TTL_MINUTES} minutes.",
    )


def register(db: Session, body: RegisterRequest) -> None:
    existing_user = db.query(UserRecord).filter(UserRecord.email == body.email).first()
    if existing_user is not None:
        raise AuthError(409, "Email already registered")

    verification = (
        db.query(VerificationCodeRecord)
        .filter(
            VerificationCodeRecord.email == body.email,
            VerificationCodeRecord.code == body.verificationCode,
        )
        .order_by(VerificationCodeRecord.id.desc())
        .first()
    )
    if verification is None:
        raise AuthError(400, "Invalid verification code")
    if verification.expires_at < datetime.utcnow():
        raise AuthError(400, "Verification code expired")

    db.add(
        UserRecord(
            email=body.email,
            password_hash=get_password_hash(body.password),
            is_verified=True,
        )
    )
    db.delete(verification)
    db.commit()


def login(db: Session, body: LoginRequest) -> TokenResponse:
    user = db.query(UserRecord).filter(UserRecord.email == body.email).first()
    if user is None:
        raise AuthError(401, "Invalid email or password")

    is_valid, new_hash = verify_password(body.password, user.password_hash)
    if not is_valid:
        raise AuthError(401, "Invalid email or password")

    if new_hash is not None:
        user.password_hash = new_hash
        db.commit()

    access_token, _ = create_access_token(user.email)
    return TokenResponse(accessToken=access_token)


def logout(db: Session, body: LogoutRequest) -> None:
    """Revokes the access token by recording its hash in RevokedTokenRecord, so a future
    token-verification dependency can reject it even though it hasn't naturally expired yet."""
    try:
        # verify_exp=False: a token that's already expired is already unusable, so still record
        # it (idempotent, no error) rather than making logout fail for a client retrying late.
        payload = decode_token(body.accessToken, verify_exp=False)
    except JWTError:
        raise AuthError(401, "Invalid token") from None

    token_hash = hash_token(body.accessToken)
    already_revoked = (
        db.query(RevokedTokenRecord).filter(RevokedTokenRecord.token_hash == token_hash).first()
    )
    if already_revoked is not None:
        return

    db.add(
        RevokedTokenRecord(
            token_hash=token_hash,
            subject=payload.get("sub"),
            expires_at=datetime.fromtimestamp(payload["exp"], tz=timezone.utc),
        )
    )
    db.commit()


def is_token_revoked(db: Session, token: str) -> bool:
    """Hook for a future token-verification dependency (none exists yet in this codebase — see
    /auth/logout) to check before accepting a bearer token."""
    return db.query(RevokedTokenRecord).filter(RevokedTokenRecord.token_hash == hash_token(token)).first() is not None
