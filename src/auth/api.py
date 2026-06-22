from fastapi import APIRouter

from src.auth.schemas.auth_schema import (
    LoginRequest,
    LogoutResponse,
    RefreshTokenRequest,
    SignupRequest,
    SignupResponse,
    TokenResponse,
    VerificationCodeRequest,
    VerificationCodeResponse,
)
from src.auth.services.auth_service import (
    login,
    logout,
    refresh_tokens,
    send_verification_code,
    signup,
)
from src.core.deps import CurrentUser, SessionDep, TokenDep

router = APIRouter(tags=["auth"])


@router.post("/signup", response_model=SignupResponse, status_code=201)
def signup_endpoint(body: SignupRequest, db: SessionDep):
    signup(db, body.email, body.password, body.code)
    return SignupResponse(code=201, msg="User signup successfully")


@router.post("/verification-code", response_model=VerificationCodeResponse)
def verification_code_endpoint(body: VerificationCodeRequest, db: SessionDep):
    exp_minute = send_verification_code(db, body.email)
    return VerificationCodeResponse(msg="Verification code sent to your email", exp_minute=exp_minute)


@router.post("/signin", response_model=TokenResponse)
def signin_endpoint(body: LoginRequest, db: SessionDep):
    return login(db, body.email, body.password)


@router.post("/refresh-token", response_model=TokenResponse)
def refresh_token_endpoint(body: RefreshTokenRequest, db: SessionDep):
    return refresh_tokens(db, body.refresh_token)


@router.post("/signout", response_model=LogoutResponse)
def signout_endpoint(db: SessionDep, current_user: CurrentUser, token: TokenDep):
    logout(db, current_user, token)
    return LogoutResponse(code=204, msg="User logout successfully")
