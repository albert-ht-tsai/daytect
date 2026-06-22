from datetime import datetime
from typing import Any, Literal, Optional

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


# --- Today metrics ---


class HeartRateMetric(BaseModel):
    unit: Literal["bpm"] = "bpm"
    current: Optional[float] = None
    avg: Optional[float] = None
    min: Optional[float] = None
    max: Optional[float] = None
    status: MetricStatus
    trend: MetricTrend


class BloodPressureMetric(BaseModel):
    unit: Literal["mmHg"] = "mmHg"
    systolic: Optional[float] = None
    diastolic: Optional[float] = None
    status: MetricStatus
    trend: MetricTrend


class BloodOxygenMetric(BaseModel):
    unit: Literal["%"] = "%"
    avg: Optional[float] = None
    min: Optional[float] = None
    status: MetricStatus
    trend: MetricTrend


class SleepMetric(BaseModel):
    unit: Literal["minutes"] = "minutes"
    light: Optional[float] = None
    deep: Optional[float] = None
    wake: Optional[float] = None
    total: Optional[float] = None
    status: MetricStatus
    trend: MetricTrend


class BodyTemperatureMetric(BaseModel):
    unit: Literal["°C"] = "°C"
    avg: Optional[float] = None
    status: MetricStatus
    trend: MetricTrend


class HrvMetric(BaseModel):
    unit: Literal["ms"] = "ms"
    avg: Optional[float] = None
    status: MetricStatus
    trend: MetricTrend


class EcgMetric(BaseModel):
    unit: str = "raw"
    status: MetricStatus
    trend: MetricTrend


class MetMetric(BaseModel):
    unit: Literal["MET"] = "MET"
    avg: Optional[float] = None
    status: MetricStatus
    trend: MetricTrend


class StressMetric(BaseModel):
    unit: str = "score"
    avg: Optional[float] = None
    status: MetricStatus
    trend: MetricTrend


class BloodComponentsMetric(BaseModel):
    unit: str = "value"
    status: MetricStatus
    trend: MetricTrend


# --- Weekly metrics ---


class WeeklyHeartRateMetric(BaseModel):
    unit: Literal["bpm"] = "bpm"
    weekly_avg: Optional[float] = None
    status: MetricStatus
    trend: MetricTrend


class WeeklyBloodPressureMetric(BaseModel):
    unit: Literal["mmHg"] = "mmHg"
    avg_systolic: Optional[float] = None
    avg_diastolic: Optional[float] = None
    status: MetricStatus
    trend: MetricTrend


class WeeklyBloodOxygenMetric(BaseModel):
    unit: Literal["%"] = "%"
    weekly_avg: Optional[float] = None
    min: Optional[float] = None
    status: MetricStatus
    trend: MetricTrend


class WeeklySleepMetric(BaseModel):
    unit: Literal["minutes"] = "minutes"
    avg_light: Optional[float] = None
    avg_deep: Optional[float] = None
    avg_wake: Optional[float] = None
    avg_total: Optional[float] = None
    status: MetricStatus
    trend: MetricTrend


class WeeklyBodyTemperatureMetric(BaseModel):
    unit: Literal["°C"] = "°C"
    weekly_avg: Optional[float] = None
    status: MetricStatus
    trend: MetricTrend


class WeeklyHrvMetric(BaseModel):
    unit: Literal["ms"] = "ms"
    weekly_avg: Optional[float] = None
    status: MetricStatus
    trend: MetricTrend


class WeeklyEcgMetric(BaseModel):
    unit: str = "raw"
    status: MetricStatus
    trend: MetricTrend


class WeeklyMetMetric(BaseModel):
    unit: Literal["MET"] = "MET"
    weekly_avg: Optional[float] = None
    status: MetricStatus
    trend: MetricTrend


class WeeklyStressMetric(BaseModel):
    unit: str = "score"
    weekly_avg: Optional[float] = None
    status: MetricStatus
    trend: MetricTrend


class WeeklyBloodComponentsMetric(BaseModel):
    unit: str = "value"
    status: MetricStatus
    trend: MetricTrend


# --- Metric containers ---


class HealthMetrics(BaseModel):
    sleep: Optional[SleepMetric] = None
    heart_rate: Optional[HeartRateMetric] = None
    blood_pressure: Optional[BloodPressureMetric] = None
    blood_oxygen: Optional[BloodOxygenMetric] = None
    body_temperature: Optional[BodyTemperatureMetric] = None
    hrv: Optional[HrvMetric] = None
    ecg: Optional[EcgMetric] = None
    met: Optional[MetMetric] = None
    stress: Optional[StressMetric] = None
    blood_components: Optional[BloodComponentsMetric] = None


class WeeklyHealthMetrics(BaseModel):
    sleep: Optional[WeeklySleepMetric] = None
    heart_rate: Optional[WeeklyHeartRateMetric] = None
    blood_pressure: Optional[WeeklyBloodPressureMetric] = None
    blood_oxygen: Optional[WeeklyBloodOxygenMetric] = None
    body_temperature: Optional[WeeklyBodyTemperatureMetric] = None
    hrv: Optional[WeeklyHrvMetric] = None
    ecg: Optional[WeeklyEcgMetric] = None
    met: Optional[WeeklyMetMetric] = None
    stress: Optional[WeeklyStressMetric] = None
    blood_components: Optional[WeeklyBloodComponentsMetric] = None


# --- health_data record types ---


class SleepRecord(BaseModel):
    start_time: Optional[str] = None
    end_time: Optional[str] = None
    date: Optional[str] = None
    light: Optional[int] = None
    deep: Optional[int] = None
    wake: Optional[int] = None
    total: Optional[int] = None
    quality: Optional[int] = None
    unit: Literal["minutes"] = "minutes"


class ValueTimeRecord(BaseModel):
    value: Any = None
    unit: str
    time: str


class BloodPressureRecord(BaseModel):
    systolic: Optional[float] = None
    diastolic: Optional[float] = None
    unit: Literal["mmHg"] = "mmHg"
    time: str


class StressRecord(BaseModel):
    value: Optional[int] = None
    unit: str
    time: str
    source_field: Literal["pressure"] = "pressure"


class HealthDataTimeline(BaseModel):
    sleep: list[SleepRecord] = []
    heart_rate: list[ValueTimeRecord] = []
    blood_pressure: list[BloodPressureRecord] = []
    blood_oxygen: list[ValueTimeRecord] = []
    body_temperature: list[ValueTimeRecord] = []
    hrv: list[ValueTimeRecord] = []
    ecg: list[ValueTimeRecord] = []
    met: list[ValueTimeRecord] = []
    stress: list[StressRecord] = []
    blood_components: list[ValueTimeRecord] = []


# --- Overview models ---


class TodayHealthOverview(BaseModel):
    date: str
    data_status: DataStatus
    message: Optional[str] = None
    health_score: HealthScore
    health_trend: HealthTrend
    health_insight: HealthInsight
    metrics: HealthMetrics
    health_data: HealthDataTimeline


class WeeklyHealthOverview(BaseModel):
    start_date: str
    end_date: str
    data_status: DataStatus
    message: Optional[str] = None
    health_score: HealthScore
    health_trend: HealthTrend
    health_insight: HealthInsight
    metrics: WeeklyHealthMetrics
    health_data: HealthDataTimeline


class DashboardData(BaseModel):
    today_health_overview: TodayHealthOverview
    weekly_health_overview: WeeklyHealthOverview
    generated_at: datetime


class DashboardResponse(BaseModel):
    success: bool = True
    data: Optional[DashboardData] = None
    message: str = "Dashboard data retrieved successfully."
