from datetime import datetime
from typing import Optional

from pydantic import BaseModel


# ── /users/me ─────────────────────────────────────────────────────────────────

class MeData(BaseModel):
    id: int
    email: str
    name: Optional[str] = None
    avatar_url: Optional[str] = None

    model_config = {"from_attributes": True}


class MeResponse(BaseModel):
    success: bool = True
    data: MeData
    message: str = "User profile retrieved successfully."


class MeUpdateRequest(BaseModel):
    name: Optional[str] = None


class MeUpdateResponse(BaseModel):
    success: bool = True
    data: None = None
    message: str = "User profile updated successfully."


# ── /users/me/avatar ─────────────────────────────────────────────────────────

class AvatarData(BaseModel):
    avatar_url: str


class AvatarUpdateResponse(BaseModel):
    success: bool = True
    data: AvatarData
    message: str = "Avatar updated successfully."


# ── /users/me/body-insight ────────────────────────────────────────────────────

class BodyInsightData(BaseModel):
    region: Optional[str] = None
    sex: Optional[str] = None
    age: Optional[int] = None
    skin_color: Optional[str] = None
    height: Optional[float] = None
    height_unit: Optional[str] = None
    weight: Optional[float] = None
    weight_unit: Optional[str] = None
    step_aim: Optional[float] = None
    step_aim_type: Optional[str] = None
    sleep_aim: Optional[float] = None
    sleep_aim_type: Optional[str] = None

    model_config = {"from_attributes": True}


class BodyInsightResponse(BaseModel):
    success: bool = True
    data: BodyInsightData
    message: str = "Body insight retrieved successfully."


class BodyInsightRequest(BaseModel):
    region: Optional[str] = None
    sex: Optional[str] = None
    age: Optional[int] = None
    skin_color: Optional[str] = None
    height: Optional[float] = None
    height_unit: Optional[str] = None
    weight: Optional[float] = None
    weight_unit: Optional[str] = None
    step_aim: Optional[float] = None
    step_aim_type: Optional[str] = None
    sleep_aim: Optional[float] = None
    sleep_aim_type: Optional[str] = None


# ── /users/me/bmi ─────────────────────────────────────────────────────────────

class BmiData(BaseModel):
    score: Optional[float] = None
    bmi_category: Optional[str] = None
    calculated_at: Optional[datetime] = None


class BmiResponse(BaseModel):
    success: bool = True
    data: BmiData
    message: str = "BMI calculated successfully."
