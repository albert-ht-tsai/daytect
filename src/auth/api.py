from fastapi import APIRouter

from src.auth.schemas.auth_schema import (
    LoginRequest,
    LoginResponse,
    LogoutResponse,
    RefreshTokenResponse,
    ResetPasswordRequest,
    ResetPasswordResponse,
    SignupRequest,
    SignupResponse,
    VerificationCodeRequest,
    VerificationCodeResponse,
)
from src.auth.services.auth_service import (
    login,
    logout,
    refresh_access_token,
    reset_password,
    send_verification_code,
    signup,
)
from src.core.deps import CurrentUser, SessionDep, TokenDep

router = APIRouter(prefix="/auth", tags=["auth"])


@router.post("/login", response_model=LoginResponse)
def login_endpoint(body: LoginRequest, db: SessionDep):
    return login(db, body.email, body.password)


@router.post("/signup", response_model=SignupResponse, status_code=201)
def signup_endpoint(body: SignupRequest, db: SessionDep):
    return signup(db, body.email, body.password, body.code)


@router.post("/verification-code", response_model=VerificationCodeResponse)
def verification_code_endpoint(body: VerificationCodeRequest, db: SessionDep):
    return send_verification_code(db, body.email, body.type)


@router.post("/refresh-token", response_model=RefreshTokenResponse)
def refresh_token_endpoint(db: SessionDep, token: TokenDep):
    return refresh_access_token(db, token)


@router.post("/logout", response_model=LogoutResponse)
def logout_endpoint(db: SessionDep, current_user: CurrentUser, token: TokenDep):
    return logout(db, current_user, token)


@router.post("/reset-password", response_model=ResetPasswordResponse)
def reset_password_endpoint(body: ResetPasswordRequest, db: SessionDep):
    return reset_password(db, body.email, body.password, body.code)
