from typing import Literal

from pydantic import BaseModel

ScoreLabel = Literal["Good", "Normal", "Recovering", "Mild Discomfort", "Sick", "Strong Attention"]


class SuggestionDetail(BaseModel):
    issue: str
    solution: str
    improvement: str


class TrendPeriod(BaseModel):
    date: str
    score: list[float]
    score_label: ScoreLabel
    suggestion: dict[str, SuggestionDetail]
    improved_by: float
    notes: dict[str, str] = {}


class HealthTrendingResponse(BaseModel):
    week: TrendPeriod
    month: TrendPeriod
    year: TrendPeriod
