from typing import Any

from pydantic import BaseModel


class DataSummaryData(BaseModel):
    macAddress: str
    reportDate: str
    startTime: str
    endTime: str
    summaryId: str
    generated: bool
    responseId: str | None = None
    report: dict[str, Any]


class DataSummaryResponse(BaseModel):
    success: bool
    data: DataSummaryData
