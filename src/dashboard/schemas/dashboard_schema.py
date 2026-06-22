from datetime import datetime
from typing import Optional

from pydantic import BaseModel

from src.report.schemas.report_schema import HealthScoreChange


class CurrentDevice(BaseModel):
    id: int
    name: str
    device_type: Optional[str] = None
    bluetooth_status: str
    sync_status: str
    battery: Optional[int] = None
    last_sync_at: Optional[datetime] = None
    illustration_key: str

    model_config = {"from_attributes": True}


class DashboardAnalysisStatus(BaseModel):
    status: str
    analysis_id: Optional[int] = None
    generated_at: Optional[datetime] = None
    message: Optional[str] = None


class DashboardHealthScore(BaseModel):
    score: int
    max_score: int = 100
    level: str
    label: str
    description: str
    change: Optional[HealthScoreChange] = None


class DashboardChartPoint(BaseModel):
    date: str
    label: str
    score: int


class DashboardHealthTrend(BaseModel):
    status: str
    summary: str
    chart_type: str = "line"
    chart: list[DashboardChartPoint]


class HealthInsightItem(BaseModel):
    metric: str
    label: str
    value: Optional[str] = None
    status: Optional[str] = None
    message: Optional[str] = None


class DashboardHealthInsight(BaseModel):
    status: str
    generated_by: Optional[str] = None
    updated_at: Optional[datetime] = None
    summary: str
    items: list[HealthInsightItem]


class CurrentHealthReport(BaseModel):
    health_score: DashboardHealthScore
    health_trend: DashboardHealthTrend
    health_insight: DashboardHealthInsight


class DeviceRangeAlert(BaseModel):
    is_active: bool
    status: str
    title: Optional[str] = None
    message: Optional[str] = None
    illustration_key: Optional[str] = None
    remind_later_minutes: int
    last_triggered_at: Optional[datetime] = None
    muted_until: Optional[datetime] = None


class ViewDetailParams(BaseModel):
    device_id: int
    range: str = "weekly"


class ViewDetail(BaseModel):
    screen: str = "health_detail"
    params: ViewDetailParams


class Navigation(BaseModel):
    view_detail: ViewDetail


class DashboardResponse(BaseModel):
    device_id: int
    date: str
    generated_at: Optional[datetime] = None
    current_device: CurrentDevice
    analysis_status: DashboardAnalysisStatus
    current_health_report: Optional[CurrentHealthReport] = None
    device_range_alert: DeviceRangeAlert
    navigation: Optional[Navigation] = None
