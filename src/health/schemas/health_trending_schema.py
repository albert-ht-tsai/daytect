from typing import Literal

from pydantic import BaseModel

ScoreLabel = Literal["Good", "Normal", "Recovering", "Mild Discomfort", "Sick", "Strong Attention"]


class TrendPeriod(BaseModel):
    date: str
    score: list[float]
    score_label: ScoreLabel
    suggestion: dict[str, str]
    improved_by: float


class HealthTrendingResponse(BaseModel):
    week: TrendPeriod
    month: TrendPeriod
    year: TrendPeriod
