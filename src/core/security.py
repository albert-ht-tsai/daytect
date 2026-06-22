from datetime import datetime, timedelta, timezone
from typing import Any
from jose import JWTError, jwt
from pwdlib import PasswordHash
from pwdlib.hashers.argon2 import Argon2Hasher
from pwdlib.hashers.bcrypt import BcryptHasher

import os

SECRET_KEY = os.getenv("SECRET_KEY")
REFRESH_SECRET_KEY = os.getenv("REFRESH_SECRET_KEY")
ALGORITHM = "HS256"

password_hash = PasswordHash(
    (
        Argon2Hasher(),
        BcryptHasher(),
    )
)

def create_access_token(subject: str | Any) -> tuple[str, datetime]:
    try:
        expire = datetime.now(timezone.utc) + timedelta(minutes=60)
        payload = {"exp": expire, "sub": str(subject), "type": "access"}
        token = jwt.encode(payload, SECRET_KEY, algorithm=ALGORITHM)
        return token, expire
    except JWTError as e:
        raise RuntimeError(f"Access token creation failed: {e}")


def create_refresh_token(subject: str | Any) -> tuple[str, datetime]:
    try:
        expire = datetime.now(timezone.utc) + timedelta(days=30)
        payload = {"exp": expire, "sub": str(subject), "type": "refresh"}
        token = jwt.encode(payload, REFRESH_SECRET_KEY, algorithm=ALGORITHM)
        return token, expire
    except JWTError as e:
        raise RuntimeError(f"Refresh token creation failed: {e}")

def verify_password(
    plain_password: str, hashed_password: str
) -> tuple[bool, str | None]:
    return password_hash.verify_and_update(plain_password, hashed_password)


def get_password_hash(password: str) -> str:
    return password_hash.hash(password)

