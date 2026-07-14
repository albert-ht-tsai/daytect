import re
from typing import Annotated

from pydantic import AfterValidator, BaseModel, Field

EMAIL_REGEX = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")


def _validate_email(value: str) -> str:
    if not EMAIL_REGEX.match(value):
        raise ValueError("Invalid email format")
    return value.lower()


EmailField = Annotated[str, AfterValidator(_validate_email)]


class SendVerificationRequest(BaseModel):
    email: EmailField


class RegisterRequest(BaseModel):
    email: EmailField
    verificationCode: str
    password: str = Field(min_length=8)


class LoginRequest(BaseModel):
    email: EmailField
    password: str


class TokenResponse(BaseModel):
    accessToken: str
    tokenType: str = "bearer"


class LogoutRequest(BaseModel):
    accessToken: str


class ResetPasswordRequest(BaseModel):
    email: EmailField
    verificationCode: str
    newPassword: str = Field(min_length=8)
