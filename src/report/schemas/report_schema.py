from datetime import datetime
from typing import Optional

from pydantic import BaseModel


class HealthScoreChange(BaseModel):
    value: int
    compare_to: str
    direction: str
    label: str


class HealthScoreBlock(BaseModel):
    score: int
    max_score: int = 100
    level: str
    label: str
    description: str
    change: Optional[HealthScoreChange] = None


class HealthTrendChartPoint(BaseModel):
    date: str
    label: str
    score: int
    risk_level: Optional[str] = None


class HealthTrend(BaseModel):
    status: str
    summary: str
    chart_type: str
    chart: list[HealthTrendChartPoint]


class InsightSection(BaseModel):
    type: str
    title: str
    status: str
    content: str


class HealthInsight(BaseModel):
    summary: str
    sections: list[InsightSection]


class MetricSummaryItem(BaseModel):
    metric: str
    label: str
    average: str
    status: str
    trend: str
    description: str


class PossibleContributor(BaseModel):
    type: str
    label: str
    severity: str
    description: str


class HealthReport(BaseModel):
    title: str
    period_label: str
    health_score: HealthScoreBlock
    health_trend: HealthTrend
    health_insight: HealthInsight
    metric_summary: list[MetricSummaryItem]
    possible_contributors: Optional[list[PossibleContributor]] = None
    recommendations: list[str]


class ReportAnalysisStatus(BaseModel):
    status: str
    analysis_id: Optional[int] = None
    generated_at: Optional[datetime] = None
    message: Optional[str] = None


class ReportResponse(BaseModel):
    device_id: int
    range: str
    start_date: str
    end_date: str
    generated_at: Optional[datetime] = None
    generated_by: Optional[str] = None
    analysis_status: ReportAnalysisStatus
    health_report: Optional[HealthReport] = None
