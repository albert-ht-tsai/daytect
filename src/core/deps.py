from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from sqlalchemy.orm import Session
from typing import Annotated, Generator
from jose import JWTError, jwt
from pydantic import ValidationError
import os
from datetime import datetime, timezone, timedelta
from dotenv import load_dotenv
from src.core.database import engine
from src.core.logging import logger
from src.profile.models.user_model import User, UserToken

load_dotenv()

SECRET_KEY = os.getenv("SECRET_KEY")
REFRESH_SECRET_KEY = os.getenv("REFRESH_SECRET_KEY")
ALGORITHM = "HS256"
bearer_scheme = HTTPBearer()


def get_db() -> Generator[Session, None, None]:
    with Session(engine) as session:
        yield session


SessionDep = Annotated[Session, Depends(get_db)]


def get_token(credentials: HTTPAuthorizationCredentials = Depends(bearer_scheme)) -> str:
    return credentials.credentials


TokenDep = Annotated[str, Depends(get_token)]


def get_current_user(db: SessionDep, token: TokenDep) -> User:
    try:
        payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
        user_id = payload.get("sub")
        if user_id is None:
            logger.warning("get_current_user: JWT has no 'sub' claim")
            raise HTTPException(status.HTTP_403_FORBIDDEN, detail={"code": 403, "message": "Invalid token"})
    except (JWTError, ValidationError) as e:
        logger.warning("get_current_user: JWT decode failed: %s", e)
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail={"code": 403, "message": "Invalid credentials"},
        )

    db_token = db.query(UserToken).filter(
        UserToken.user_id == int(user_id),
        UserToken.access_token == token,
        UserToken.revoked == False,
    ).first()

    if not db_token:
        any_token = db.query(UserToken).filter(UserToken.user_id == int(user_id)).first()
        if not any_token:
            logger.warning("get_current_user: no UserToken row for user_id=%s", user_id)
        elif any_token.revoked:
            logger.warning("get_current_user: token is revoked for user_id=%s", user_id)
        else:
            logger.warning(
                "get_current_user: access_token mismatch for user_id=%s (stored prefix=%s, received prefix=%s)",
                user_id,
                str(any_token.access_token)[:20] if any_token.access_token else None,
                str(token)[:20],
            )
        raise HTTPException(
            status_code=403,
            detail={"code": 403, "message": "Token revoked or replaced"},
        )

    expire = db_token.access_token_expire
    now = datetime.now(timezone.utc)
    if expire.tzinfo is None:
        expire = expire.replace(tzinfo=timezone.utc)
    if expire < now:
        logger.warning("get_current_user: token expired for user_id=%s expire=%s now=%s", user_id, expire, now)
        raise HTTPException(
            status_code=403,
            detail={"code": 403, "message": "Token expired"},
        )

    db_user = db.query(User).filter(User.id == int(user_id)).first()
    if not db_user:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail={"code": 404, "message": "User not found"})

    if not db_user.is_active:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, detail={"code": 400, "message": "Inactive User"})

    return db_user


CurrentUser = Annotated[User, Depends(get_current_user)]


def get_current_user_from_refresh(db: SessionDep, token: TokenDep) -> User:
    try:
        payload = jwt.decode(token, REFRESH_SECRET_KEY, algorithms=[ALGORITHM])
        user_id = payload.get("sub")
        if user_id is None or payload.get("type") != "refresh":
            raise HTTPException(status.HTTP_403_FORBIDDEN, detail={"code": 403, "message": "Invalid refresh token"})
    except (JWTError, ValidationError):
        raise HTTPException(status.HTTP_403_FORBIDDEN, detail={"code": 403, "message": "Invalid refresh token"})

    db_token = db.query(UserToken).filter(
        UserToken.user_id == int(user_id),
        UserToken.refresh_token == token,
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

    db_user = db.query(User).filter(User.id == int(user_id)).first()
    if not db_user:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail={"code": 404, "message": "User not found"})
    if not db_user.is_active:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, detail={"code": 400, "message": "Inactive user"})

    return db_user


RefreshCurrentUser = Annotated[User, Depends(get_current_user_from_refresh)]