from typing import Literal

from pydantic import BaseModel


class ProfileInfo(BaseModel):
    sex: str
    age: int
    height: float
    weight: float
    allergy: str
    medicalHistory: str


class ProfileSummaryData(BaseModel):
    macAddress: str
    profile: ProfileInfo
    level: Literal["normal", "low", "attention"]
    levelLabel: str
    standard: str
    summary: str
    previousResponseId: str | None = None
    responseId: str | None = None


class ProfileSummaryResponse(BaseModel):
    success: bool
    data: ProfileSummaryData
