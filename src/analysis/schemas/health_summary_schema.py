from typing import Any

from pydantic import BaseModel


class HealthSummaryData(BaseModel):
    macAddress: str
    previousResponseId: str
    responseId: str
    healthSummary: dict[str, Any]


class HealthSummaryResponse(BaseModel):
    success: bool
    data: HealthSummaryData
