from datetime import datetime
from typing import Literal

from pydantic import BaseModel


# ── POST /auth/login ──────────────────────────────────────────────────────────

class LoginRequest(BaseModel):
    email: str
    password: str


class LoginUser(BaseModel):
    id: int
    email: str
    name: str | None = None
    avatar: str | None = None
    region: str | None = None

    model_config = {"from_attributes": True}


class LoginData(BaseModel):
    access_token: str
    refresh_token: str
    expires_in: int
    user: LoginUser


class LoginResponse(BaseModel):
    success: bool = True
    data: LoginData
    message: str = "User login successfully."


# ── POST /auth/signup ─────────────────────────────────────────────────────────

class SignupRequest(BaseModel):
    email: str
    password: str
    code: str


class SignupData(BaseModel):
    id: int
    email: str
    name: str | None = None
    created_at: datetime

    model_config = {"from_attributes": True}


class SignupResponse(BaseModel):
    success: bool = True
    data: SignupData
    message: str = "Account created successfully."


# ── POST /auth/verification-code ──────────────────────────────────────────────

class VerificationCodeRequest(BaseModel):
    email: str
    type: Literal["signup", "reset"]


class VerificationCodeData(BaseModel):
    expires_in: int


class VerificationCodeResponse(BaseModel):
    success: bool = True
    data: VerificationCodeData
    message: str = "Verification code sent successfully."


# ── POST /auth/refresh-token ──────────────────────────────────────────────────

class RefreshTokenData(BaseModel):
    access_token: str
    expires_in: int


class RefreshTokenResponse(BaseModel):
    success: bool = True
    data: RefreshTokenData
    message: str = "Access token refreshed successfully."


# ── POST /auth/logout ─────────────────────────────────────────────────────────

class LogoutResponse(BaseModel):
    success: bool = True
    data: None = None
    message: str = "User logout successfully."


# ── POST /auth/reset-password ─────────────────────────────────────────────────

class ResetPasswordRequest(BaseModel):
    email: str
    password: str
    code: str


class ResetPasswordResponse(BaseModel):
    success: bool = True
    data: None = None
    message: str = "Password reset successfully."
