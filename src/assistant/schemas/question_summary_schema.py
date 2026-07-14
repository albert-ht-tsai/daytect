from typing import Any

from pydantic import BaseModel


class QuestionSummaryData(BaseModel):
    macAddress: str
    category: str | None = None
    intent: str | None = None
    confidence: float
    # A {conclusion, basis, suggestion, warning} object for most intents, a time-of-day-segmented
    # object for "計畫規劃", or a plain string when inScope is false — see question_prompt.md.
    response: Any
    benefits: list[dict[str, Any]]
    responseId: str | None = None


class QuestionSummaryResponse(BaseModel):
    success: bool
    data: QuestionSummaryData
