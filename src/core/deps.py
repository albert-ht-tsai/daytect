from sqlalchemy.orm import Session
from typing import Annotated, Generator
from fastapi import Depends
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from jose import JWTError
from src.core.database import engine
from src.core.security import decode_token


class AuthenticationError(Exception):
    """Raised by get_current_user_id when no valid access token is present. A plain HTTPException
    here would bypass every module's own {"success": false, "error": {...}} _error_response
    helper (dependencies raise before the route body runs) and fall back to FastAPI's default
    {"detail": ...} shape instead — see the app-wide handler registered in src/main.py, which is
    what keeps this on the same envelope as every other error in health_report/assistant."""

    def __init__(self, message: str = "Missing or invalid access token", code: str = "UNAUTHORIZED"):
        super().__init__(message)
        self.message = message
        self.code = code


def get_db() -> Generator[Session, None, None]:
    with Session(engine) as session:
        yield session


SessionDep = Annotated[Session, Depends(get_db)]

# auto_error=False so a missing/malformed header falls through to our own {"code","message"}
# 401 shape (see get_current_user_id) instead of Starlette's default error body. Registering this
# as a proper OpenAPI security scheme (rather than reading a raw `Authorization` Header(...)) is
# what gives Swagger UI a single global "Authorize" button — paste the token once and it's
# attached to every route below that depends on CurrentUserId/OptionalUserId, instead of having to
# paste "Bearer <token>" into each endpoint's own Authorization field.
_bearer_scheme = HTTPBearer(
    auto_error=False,
    scheme_name="BearerAuth",
    bearerFormat="JWT",
    description="Paste the accessToken returned by POST /v1/auth/login (without the word 'Bearer').",
)


def _resolve_user_id(db: Session, token: str | None) -> int | None:
    """Returns the numeric user id for a bearer token, or None if the token is missing, doesn't
    decode, or no user matches.

    The access token's `sub` claim is the user's *email* (see auth_service.login ->
    create_access_token(user.email)), not the numeric id, so this always needs a DB lookup to
    translate email -> id — it can't be done from the token alone."""
    if not token:
        return None
    try:
        payload = decode_token(token)
    except JWTError:
        return None
    email = payload.get("sub")
    if not email:
        return None
    # Local import to avoid a module-load-order cycle between core.deps and auth.models.
    from src.auth.models.user_model import UserRecord

    user = db.query(UserRecord).filter(UserRecord.email == email).first()
    return user.id if user else None


def get_current_user_id(
    db: SessionDep,
    credentials: Annotated[HTTPAuthorizationCredentials | None, Depends(_bearer_scheme)] = None,
) -> int:
    """Required auth dependency: raises 401 when no valid access token is present.

    First route-level auth enforcement in this codebase — token issuing/revocation already
    existed (src/core/security.py, src/auth/services/auth_service.py) but nothing previously
    checked the Authorization header on any endpoint.
    """
    user_id = _resolve_user_id(db, credentials.credentials if credentials else None)
    if user_id is None:
        raise AuthenticationError()
    return user_id


def get_optional_user_id(
    db: SessionDep,
    credentials: Annotated[HTTPAuthorizationCredentials | None, Depends(_bearer_scheme)] = None,
) -> int | None:
    """Best-effort auth: returns the user id if a valid token is present, else None without
    raising — for endpoints that must keep working for unauthenticated callers but can opportunis-
    tically attach the caller's identity when they are logged in (see POST /v1/device)."""
    return _resolve_user_id(db, credentials.credentials if credentials else None)


CurrentUserId = Annotated[int, Depends(get_current_user_id)]
OptionalUserId = Annotated[int | None, Depends(get_optional_user_id)]