from datetime import datetime
from typing import Literal, Optional

from pydantic import BaseModel

DataStatus = Literal["sufficient", "insufficient", "no_data"]
HealthLevel = Literal["excellent", "good", "fair", "poor", "critical", "unknown"]
TrendCompare = Literal["yesterday", "latest_7_days"]
TrendDirection = Literal["improved", "declined", "stable", "insufficient_data"]
HighlightType = Literal["positive", "warning", "risk", "info"]
MetricStatus = Literal["normal", "good", "low", "high", "abnormal", "unknown"]
MetricTrend = Literal["improved", "declined", "stable", "insufficient_data"]


class HealthScore(BaseModel):
    score: Optional[int] = None
    avg_score: Optional[int] = None
    level: HealthLevel
    summary: Optional[str] = None


class HealthTrend(BaseModel):
    compare_with: TrendCompare
    trend: TrendDirection
    score_change: Optional[int] = None
    summary: Optional[str] = None


class HealthHighlight(BaseModel):
    type: HighlightType
    metric: str
    title: str
    description: str


class HealthInsight(BaseModel):
    is_available: bool
    summary: Optional[str] = None
    highlights: list[HealthHighlight] = []


class HeartRateMetric(BaseModel):
    unit: Literal["bpm"] = "bpm"
    current: Optional[float] = None
    avg: Optional[float] = None
    min: Optional[float] = None
    max: Optional[float] = None
    status: MetricStatus
    trend: MetricTrend


class WeeklyHeartRateMetric(BaseModel):
    unit: Literal["bpm"] = "bpm"
    weekly_avg: Optional[float] = None
    status: MetricStatus
    trend: MetricTrend


class BloodPressureMetric(BaseModel):
    unit: Literal["mmHg"] = "mmHg"
    systolic: Optional[float] = None
    diastolic: Optional[float] = None
    status: MetricStatus
    trend: MetricTrend


class WeeklyBloodPressureMetric(BaseModel):
    unit: Literal["mmHg"] = "mmHg"
    avg_systolic: Optional[float] = None
    avg_diastolic: Optional[float] = None
    status: MetricStatus
    trend: MetricTrend


class BloodOxygenMetric(BaseModel):
    unit: Literal["%"] = "%"
    avg: Optional[float] = None
    min: Optional[float] = None
    status: MetricStatus
    trend: MetricTrend


class WeeklyBloodOxygenMetric(BaseModel):
    unit: Literal["%"] = "%"
    weekly_avg: Optional[float] = None
    min: Optional[float] = None
    status: MetricStatus
    trend: MetricTrend


class SleepMetric(BaseModel):
    unit: Literal["hours"] = "hours"
    duration: Optional[float] = None
    quality_score: Optional[int] = None
    status: MetricStatus
    trend: MetricTrend


class WeeklySleepMetric(BaseModel):
    unit: Literal["hours"] = "hours"
    avg_duration: Optional[float] = None
    avg_quality_score: Optional[int] = None
    status: MetricStatus
    trend: MetricTrend


class BodyTemperatureMetric(BaseModel):
    unit: Literal["°C"] = "°C"
    avg: Optional[float] = None
    status: MetricStatus
    trend: MetricTrend


class WeeklyBodyTemperatureMetric(BaseModel):
    unit: Literal["°C"] = "°C"
    weekly_avg: Optional[float] = None
    status: MetricStatus
    trend: MetricTrend


class ActivityMetric(BaseModel):
    steps: Optional[float] = None
    calories: Optional[float] = None
    active_minutes: Optional[float] = None
    status: MetricStatus
    trend: MetricTrend


class WeeklyActivityMetric(BaseModel):
    avg_steps: Optional[float] = None
    avg_calories: Optional[float] = None
    avg_active_minutes: Optional[float] = None
    status: MetricStatus
    trend: MetricTrend


class HealthMetrics(BaseModel):
    heart_rate: Optional[HeartRateMetric] = None
    blood_pressure: Optional[BloodPressureMetric] = None
    blood_oxygen: Optional[BloodOxygenMetric] = None
    sleep: Optional[SleepMetric] = None
    body_temperature: Optional[BodyTemperatureMetric] = None
    activity: Optional[ActivityMetric] = None


class WeeklyHealthMetrics(BaseModel):
    heart_rate: Optional[WeeklyHeartRateMetric] = None
    blood_pressure: Optional[WeeklyBloodPressureMetric] = None
    blood_oxygen: Optional[WeeklyBloodOxygenMetric] = None
    sleep: Optional[WeeklySleepMetric] = None
    body_temperature: Optional[WeeklyBodyTemperatureMetric] = None
    activity: Optional[WeeklyActivityMetric] = None


class TodayHealthOverview(BaseModel):
    date: str
    data_status: DataStatus
    message: Optional[str] = None
    health_score: HealthScore
    health_trend: HealthTrend
    health_insight: HealthInsight
    metrics: HealthMetrics


class WeeklyHealthOverview(BaseModel):
    start_date: str
    end_date: str
    data_status: DataStatus
    message: Optional[str] = None
    health_score: HealthScore
    health_trend: HealthTrend
    health_insight: HealthInsight
    metrics: WeeklyHealthMetrics


class DashboardData(BaseModel):
    today_health_overview: TodayHealthOverview
    weekly_health_overview: WeeklyHealthOverview
    generated_at: datetime


class DashboardResponse(BaseModel):
    success: bool = True
    data: Optional[DashboardData] = None
    message: str = "Dashboard data retrieved successfully."
