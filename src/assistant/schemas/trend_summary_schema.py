from typing import Any

from pydantic import BaseModel


class TrendSummaryData(BaseModel):
    macAddress: str
    startDate: str
    endDate: str
    levelConsistent: bool
    reassessedLevel: str | None = None
    reassessedStandard: str | None = None
    trendData: dict[str, Any]
    overallSummary: str = ""
    todayRecommendations: list[str] = []
    sleep: dict[str, Any]
    health: dict[str, Any]
    activity: dict[str, Any]
    responseId: str | None = None


class TrendSummaryResponse(BaseModel):
    success: bool
    data: TrendSummaryData
