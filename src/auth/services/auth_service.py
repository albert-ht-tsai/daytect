import random
from datetime import datetime, timedelta

from sqlalchemy.orm import Session

from src.auth.models.user_model import UserRecord
from src.auth.models.verification_code_model import VerificationCodeRecord
from src.auth.schemas.auth_schema import (
    LoginRequest,
    RegisterRequest,
    SendVerificationRequest,
    TokenResponse,
)
from src.auth.services.errors import AuthError
from src.core.email import send_email
from src.core.security import (
    create_access_token,
    create_refresh_token,
    get_password_hash,
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
    refresh_token, _ = create_refresh_token(user.email)
    return TokenResponse(accessToken=access_token, refreshToken=refresh_token)
