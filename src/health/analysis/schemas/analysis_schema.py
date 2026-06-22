from datetime import datetime
from typing import Optional

from pydantic import BaseModel


class TriggerAnalysisRequest(BaseModel):
    date: str
    range: str
    include_metrics: Optional[list[str]] = None


class TriggerAnalysisData(BaseModel):
    analysis_id: int
    device_id: int
    date: str
    range: str
    status: str


class AnalysisStatusData(BaseModel):
    analysis_id: int
    device_id: int
    range: str
    status: str
    generated_at: Optional[datetime] = None
    message: Optional[str] = None


class AvailableAnalysisDatesResponse(BaseModel):
    range: str
    dates: list[str]


class OverallScore(BaseModel):
    score: int
    max_score: int = 100
    level: str
    description: str


class TrendSummary(BaseModel):
    status: str
    content: str


class Abnormality(BaseModel):
    metric: str
    level: str
    content: str


class KeyInsight(BaseModel):
    title: str
    content: str
    status: str


class DailyAnalysisStatus(BaseModel):
    status: str
    message: Optional[str] = None


class DailyAnalysisResponse(BaseModel):
    analysis_id: Optional[int] = None
    device_id: int
    date: str
    range: str = "daily"
    generated_by: Optional[str] = None
    generated_at: Optional[datetime] = None
    analysis_status: DailyAnalysisStatus
    summary: Optional[str] = None
    overall_score: Optional[OverallScore] = None
    trend_summary: Optional[TrendSummary] = None
    abnormalities: Optional[list[Abnormality]] = None
    key_insights: Optional[list[KeyInsight]] = None
    recommendations: Optional[list[str]] = None
