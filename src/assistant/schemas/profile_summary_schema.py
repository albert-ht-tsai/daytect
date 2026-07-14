from typing import Literal

from pydantic import BaseModel


class ProfileInfo(BaseModel):
    sex: str
    age: int
    height: float
    weight: float
    bmi: float
    bmiCategory: str
    allergy: str
    medicalHistory: str


class ProfileSummaryData(BaseModel):
    macAddress: str
    profile: ProfileInfo
    level: Literal["normal", "low", "attention"]
    levelLabel: str
    standard: str
    summary: str
    responseId: str | None = None


class ProfileSummaryResponse(BaseModel):
    success: bool
    data: ProfileSummaryData
