from fastapi import APIRouter
from fastapi.responses import JSONResponse

from src.auth.schemas.auth_schema import (
    LoginRequest,
    RegisterRequest,
    SendVerificationRequest,
    TokenResponse,
)
from src.auth.services import auth_service
from src.auth.services.errors import AuthError
from src.core.deps import SessionDep

router = APIRouter(prefix="/auth", tags=["auth"])


def _error_response(error: AuthError) -> JSONResponse:
    return JSONResponse(
        status_code=error.status_code,
        content={"success": False, "message": error.message, "data": None},
    )


@router.post("/send-verification")
def send_verification_endpoint(body: SendVerificationRequest, db: SessionDep):
    try:
        auth_service.send_verification_code(db, body)
    except AuthError as e:
        return _error_response(e)
    return {"success": True, "message": "Verification code sent"}


@router.post("/register")
def register_endpoint(body: RegisterRequest, db: SessionDep):
    try:
        auth_service.register(db, body)
    except AuthError as e:
        return _error_response(e)
    return {"success": True, "message": "Registration successful"}


@router.post("/login", response_model=TokenResponse)
def login_endpoint(body: LoginRequest, db: SessionDep):
    try:
        result = auth_service.login(db, body)
    except AuthError as e:
        return _error_response(e)
    return result
