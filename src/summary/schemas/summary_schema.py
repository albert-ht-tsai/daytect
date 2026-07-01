from typing import Literal

from pydantic import BaseModel


class SummaryRequest(BaseModel):
    macAddress: str
    date: str
    language: Literal["en", "zh"] = "en"


class CategoryResult(BaseModel):
    score: float | None = None
    summary: str | None = None
    suggestion: str | None = None


class OverallResult(BaseModel):
    score: float | None = None
    summary: str | None = None
    suggestion: str | None = None


class SummaryRecords(BaseModel):
    sleep: CategoryResult
    activity: CategoryResult
    health: CategoryResult


class DailyHealthSummaryResponse(BaseModel):
    id: str
    name: str | None
    macAddress: str
    date: str
    records: SummaryRecords
    overall: OverallResult
