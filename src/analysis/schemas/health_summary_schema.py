from typing import Any

from pydantic import BaseModel


class HealthSummaryRequest(BaseModel):
    macAddress: str
    userInput: str
    previousResponseId: str


class HealthSummaryData(BaseModel):
    macAddress: str
    previousResponseId: str
    responseId: str
    healthSummary: dict[str, Any]


class HealthSummaryResponse(BaseModel):
    success: bool
    data: HealthSummaryData
