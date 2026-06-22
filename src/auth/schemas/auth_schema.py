from pydantic import BaseModel


class SignupRequest(BaseModel):
    email: str
    password: str
    code: str


class SignupResponse(BaseModel):
    code: int
    msg: str


class VerificationCodeRequest(BaseModel):
    email: str


class VerificationCodeResponse(BaseModel):
    msg: str
    exp_minute: int


class LoginRequest(BaseModel):
    email: str
    password: str


class TokenUserInfo(BaseModel):
    id: int
    email: str
    name: str | None = None


class TokenData(BaseModel):
    access_token: str
    refresh_token: str
    expires_in: int
    user: TokenUserInfo


class TokenResponse(BaseModel):
    success: bool = True
    data: TokenData
    message: str


class RefreshTokenRequest(BaseModel):
    refresh_token: str


class LogoutResponse(BaseModel):
    code: int
    msg: str
