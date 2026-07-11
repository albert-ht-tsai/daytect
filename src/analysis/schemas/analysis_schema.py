from typing import Literal

from pydantic import BaseModel


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


class PromptPreviewRequest(BaseModel):
    """Debug-only: same inputs as /request (minus image, which requires an OpenAI vision call
    this endpoint must never make)."""

    macAddress: str
    session_id: str | None = None
    message: str
    prev_summary: str | None = None
    language: Literal["en", "zh"] = "en"


class PromptPreviewResponse(BaseModel):
    success: bool
    session_id: str
    previousResponseId: str | None = None
    systemPrompt: str
    payload: dict
    userPrompt: str
