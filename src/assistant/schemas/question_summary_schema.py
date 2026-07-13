from typing import Any

from pydantic import BaseModel


class QuestionSummaryData(BaseModel):
    macAddress: str
    category: str | None = None
    confidence: float
    response: Any
    benefits: list[dict[str, Any]]
    previousResponseId: str
    responseId: str | None = None


class QuestionSummaryResponse(BaseModel):
    success: bool
    data: QuestionSummaryData
