import hashlib
from datetime import datetime, timedelta, timezone
from typing import Any
from jose import JWTError, jwt
from pwdlib import PasswordHash
from pwdlib.hashers.argon2 import Argon2Hasher
from pwdlib.hashers.bcrypt import BcryptHasher

import os

SECRET_KEY = os.getenv("SECRET_KEY")
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


def decode_token(token: str, verify_exp: bool = True) -> dict[str, Any]:
    """Raises JWTError (including its ExpiredSignatureError subclass) on a bad signature or, when
    verify_exp is True, an expired token. Logout passes verify_exp=False so an already-expired
    token can still be revoked without erroring — it's harmless bookkeeping since an expired
    token is already unusable, and it keeps logout idempotent for clients retrying late."""
    return jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM], options={"verify_exp": verify_exp})


def hash_token(token: str) -> str:
    """One-way digest used as the revoked-token lookup key, so the raw bearer token itself is
    never persisted at rest."""
    return hashlib.sha256(token.encode()).hexdigest()


def verify_password(
    plain_password: str, hashed_password: str
) -> tuple[bool, str | None]:
    return password_hash.verify_and_update(plain_password, hashed_password)


def get_password_hash(password: str) -> str:
    return password_hash.hash(password)

