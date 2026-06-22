import random
import smtplib
from datetime import datetime, timedelta, timezone

from fastapi import HTTPException, status
from jose import JWTError, jwt
from sqlalchemy.orm import Session

from src.core.logging import logger

from src.auth.models.verification_code_model import VerificationCode
from src.core.email import send_email
from src.core.security import (
    ALGORITHM,
    REFRESH_SECRET_KEY,
    create_access_token,
    create_refresh_token,
    get_password_hash,
    verify_password,
)
from src.user.models.user_model import User, UserToken

CODE_EXP_MINUTE = 5
ACCESS_TOKEN_EXP_MINUTE = 60
REFRESH_TOKEN_EXP_DAY = 30


def send_verification_code(db: Session, email: str) -> int:
    code = str(random.randint(1000, 9999))
    expire_at = datetime.now(timezone.utc) + timedelta(minutes=CODE_EXP_MINUTE)

    existing = db.query(VerificationCode).filter(VerificationCode.email == email).first()
    if existing:
        existing.code = code
        existing.expire_at = expire_at
    else:
        db.add(VerificationCode(email=email, code=code, expire_at=expire_at))
    db.commit()

    try:
        send_email(
            to=email,
            subject="Your Verification Code",
            body=(
                f"Your verification code is: {code}\n\n"
                f"This code will expire in {CODE_EXP_MINUTE} minutes.\n"
                "If you did not request this, please ignore this email."
            ),
        )
    except smtplib.SMTPException:
        # Keep the code in DB so the user can retry signup once email is fixed.
        # Log the code so developers can retrieve it from app logs during local testing.
        logger.warning("SMTP failed for %s — verification code (dev only): %s", email, code)
        raise HTTPException(
            status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail={"code": 500, "message": "Failed to send verification email, please try again"},
        )

    return CODE_EXP_MINUTE


def signup(db: Session, email: str, password: str, code: str) -> User:
    if db.query(User).filter(User.email == email).first():
        raise HTTPException(
            status.HTTP_400_BAD_REQUEST,
            detail={"code": 400, "message": "Email already registered"},
        )

    vc = db.query(VerificationCode).filter(VerificationCode.email == email).first()
    if not vc:
        raise HTTPException(
            status.HTTP_400_BAD_REQUEST,
            detail={"code": 400, "message": "Verification code not found"},
        )
    if vc.code != code:
        raise HTTPException(
            status.HTTP_400_BAD_REQUEST,
            detail={"code": 400, "message": "Invalid verification code"},
        )

    expire_at = vc.expire_at
    if expire_at.tzinfo is None:
        expire_at = expire_at.replace(tzinfo=timezone.utc)
    if expire_at < datetime.now(timezone.utc):
        raise HTTPException(
            status.HTTP_400_BAD_REQUEST,
            detail={"code": 400, "message": "Verification code expired"},
        )

    user = User(email=email, password=get_password_hash(password))
    db.add(user)
    db.delete(vc)
    db.commit()
    db.refresh(user)
    return user


def login(db: Session, email: str, password: str) -> dict:
    user = db.query(User).filter(User.email == email).first()
    if not user:
        raise HTTPException(
            status.HTTP_400_BAD_REQUEST,
            detail={"code": 400, "message": "Invalid credentials"},
        )

    valid, updated_hash = verify_password(password, user.password)
    if not valid:
        raise HTTPException(
            status.HTTP_400_BAD_REQUEST,
            detail={"code": 400, "message": "Invalid credentials"},
        )

    if updated_hash:
        user.password = updated_hash
        db.add(user)

    access_token, access_expire = create_access_token(str(user.id))
    refresh_token, refresh_expire = create_refresh_token(str(user.id))

    db.query(UserToken).filter(
        UserToken.user_id == user.id,
        UserToken.revoked == False,  # noqa: E712
    ).update({"revoked": True})

    db.add(UserToken(
        user_id=user.id,
        access_token=access_token,
        refresh_token=refresh_token,
        access_token_expire=access_expire,
        refresh_token_expire=refresh_expire,
    ))
    db.commit()

    return {
        "success": True,
        "data": {
            "access_token": access_token,
            "refresh_token": refresh_token,
            "expires_in": ACCESS_TOKEN_EXP_MINUTE * 60,
            "user": {
                "id": user.id,
                "email": user.email,
                "name": user.name,
            },
        },
        "message": "Signed in successfully.",
    }


def refresh_tokens(db: Session, refresh_token: str) -> dict:
    try:
        payload = jwt.decode(refresh_token, REFRESH_SECRET_KEY, algorithms=[ALGORITHM])
        user_id = payload.get("sub")
        if user_id is None or payload.get("type") != "refresh":
            raise HTTPException(status.HTTP_403_FORBIDDEN, detail={"code": 403, "message": "Invalid refresh token"})
    except JWTError:
        raise HTTPException(status.HTTP_403_FORBIDDEN, detail={"code": 403, "message": "Invalid refresh token"})

    db_token = db.query(UserToken).filter(
        UserToken.user_id == int(user_id),
        UserToken.refresh_token == refresh_token,
        UserToken.revoked == False,  # noqa: E712
    ).first()
    if not db_token:
        raise HTTPException(status.HTTP_403_FORBIDDEN, detail={"code": 403, "message": "Token revoked or not found"})

    expire = db_token.refresh_token_expire
    now = datetime.now(timezone.utc)
    if expire.tzinfo is None:
        expire = expire.replace(tzinfo=timezone.utc)
    if expire < now:
        raise HTTPException(status.HTTP_403_FORBIDDEN, detail={"code": 403, "message": "Refresh token expired"})

    db_token.revoked = True

    new_access_token, new_access_expire = create_access_token(str(user_id))
    new_refresh_token, new_refresh_expire = create_refresh_token(str(user_id))

    db.add(UserToken(
        user_id=int(user_id),
        access_token=new_access_token,
        refresh_token=new_refresh_token,
        access_token_expire=new_access_expire,
        refresh_token_expire=new_refresh_expire,
    ))
    db.commit()

    user = db.query(User).filter(User.id == int(user_id)).first()

    return {
        "success": True,
        "data": {
            "access_token": new_access_token,
            "refresh_token": new_refresh_token,
            "expires_in": ACCESS_TOKEN_EXP_MINUTE * 60,
            "user": {
                "id": user.id,
                "email": user.email,
                "name": user.name,
            },
        },
        "message": "Token refreshed successfully.",
    }


def logout(db: Session, user: User, token: str) -> None:
    db.query(UserToken).filter(
        UserToken.user_id == user.id,
        UserToken.access_token == token,
    ).update({"revoked": True})
    db.commit()
