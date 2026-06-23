from typing import Optional

from pydantic import BaseModel


# ── /users/me ─────────────────────────────────────────────────────────────────

class MeResponse(BaseModel):
    id: int
    email: str
    name: Optional[str] = None
    avatar: Optional[str] = None
    region: Optional[str] = None

    model_config = {"from_attributes": True}


class MeUpdateRequest(BaseModel):
    name: Optional[str] = None
    avatar: Optional[str] = None
    region: Optional[str] = None


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

class BodyInsightGoals(BaseModel):
    step_aim: Optional[float] = None
    step_aim_type: Optional[str] = None
    sleep_aim: Optional[float] = None
    sleep_aim_type: Optional[str] = None


class BodyInsightBmi(BaseModel):
    value: Optional[float] = None
    level: Optional[str] = None


class BodyInsightData(BaseModel):
    user_id: int
    height: Optional[float] = None
    height_unit: Optional[str] = None
    weight: Optional[float] = None
    weight_unit: Optional[str] = None
    age: Optional[int] = None
    sex: Optional[str] = None
    goals: BodyInsightGoals
    bmi: BodyInsightBmi


class BodyInsightResponse(BaseModel):
    success: bool = True
    data: BodyInsightData
    message: str = "Body insight retrieved successfully."


class BodyInsightRequest(BaseModel):
    height: Optional[float] = None
    height_unit: Optional[str] = None
    weight: Optional[float] = None
    weight_unit: Optional[str] = None
    age: Optional[int] = None
    sex: Optional[str] = None
    step_aim: Optional[float] = None
    step_aim_type: Optional[str] = None
    sleep_aim: Optional[float] = None
    sleep_aim_type: Optional[str] = None
