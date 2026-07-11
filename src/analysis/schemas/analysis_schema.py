from typing import Literal

from pydantic import BaseModel


class LatestSummary(BaseModel):
    """Latest health snapshot supplied directly by the frontend (e.g. from a manual ECG
    detection callback / local healthData cache), not yet necessarily persisted to the
    backend database. Sent alongside the backend's own 7-day database average so the AI
    reply can reflect the freshest reading available."""

    heartRate: float | None = None
    systolic: float | None = None
    diastolic: float | None = None
    bloodOxygen: float | None = None
    bodyTemperature: float | None = None
    fatigueDegree: float | None = None
    ppg: list[float] | None = None
    measuredAt: str | None = None


class AnalysisResponse(BaseModel):
    success: bool
    healthSummary: str
    fatigueSummary: str
    recoverySummary: str
    session_id: str


class CompactSummaryRequest(BaseModel):
    macAddress: str
    session_id: str
    language: Literal["en", "zh"] = "en"


class CompactSummaryResponse(BaseModel):
    success: bool
    message: list[str]
    session_id: str
    source_count: int
