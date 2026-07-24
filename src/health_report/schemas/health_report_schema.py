from typing import Literal

from pydantic import BaseModel

ReportType = Literal["latest_health_summary"]
Language = Literal["zh-TW", "en"]


class HealthReportCreateRequest(BaseModel):
    report_type: ReportType = "latest_health_summary"
    language: Language = "zh-TW"
    include_ai_analysis: bool = True
    # Optional anchor date (YYYY-MM-DD): the 7-day period ends on this date (inclusive) instead of
    # defaulting to "yesterday". Validated/parsed in report_stats_service.compute_period.
    date: str | None = None
