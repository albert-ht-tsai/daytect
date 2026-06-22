from datetime import datetime
from typing import Optional

from pydantic import BaseModel


class SleepData(BaseModel):
    start_time: Optional[datetime] = None
    end_time: Optional[datetime] = None
    light: Optional[float] = None
    deep: Optional[float] = None
    wake: Optional[float] = None
    total: Optional[float] = None
    unit: Optional[str] = "minutes"


class HeartRateReading(BaseModel):
    time: datetime
    value: float
    unit: Optional[str] = "bpm"


class BloodPressureData(BaseModel):
    systolic: Optional[float] = None
    diastolic: Optional[float] = None
    unit: Optional[str] = "mmHg"


class BloodOxygenData(BaseModel):
    value: Optional[float] = None
    unit: Optional[str] = "%"


class BodyTemperatureData(BaseModel):
    value: Optional[float] = None
    unit: Optional[str] = "celsius"


class HrvData(BaseModel):
    value: Optional[float] = None
    unit: Optional[str] = "ms"


class MetData(BaseModel):
    value: Optional[float] = None
    unit: Optional[str] = "MET"
    time: Optional[datetime] = None


class EcgData(BaseModel):
    status: Optional[str] = None
    file_url: Optional[str] = None


class StressData(BaseModel):
    value: Optional[float] = None
    level: Optional[str] = None


class ActivityData(BaseModel):
    steps: Optional[float] = None
    calories: Optional[float] = None
    distance: Optional[float] = None
    distance_unit: Optional[str] = "km"


class UploadHealthDataRequest(BaseModel):
    recorded_at: datetime
    sleep: Optional[SleepData] = None
    heart_rate: Optional[list[HeartRateReading]] = None
    blood_pressure: Optional[BloodPressureData] = None
    blood_oxygen: Optional[BloodOxygenData] = None
    body_temperature: Optional[BodyTemperatureData] = None
    hrv: Optional[HrvData] = None
    ecg: Optional[EcgData] = None
    met: Optional[list[MetData]] = None
    stress: Optional[StressData] = None
    activity: Optional[ActivityData] = None
    blood_components: Optional[dict] = None


class UploadHealthDataResponseData(BaseModel):
    health_record_id: str


class AvailableDatesResponse(BaseModel):
    dates: list[str]


class MetricStatusValue(BaseModel):
    value: float | str | None = None
    unit: Optional[str] = None
    status: Optional[str] = None


class BloodPressureMetric(BaseModel):
    systolic: Optional[float] = None
    diastolic: Optional[float] = None
    unit: Optional[str] = None
    status: Optional[str] = None


class HealthDataMetrics(BaseModel):
    heart_rate: Optional[MetricStatusValue] = None
    hrv: Optional[MetricStatusValue] = None
    blood_pressure: Optional[BloodPressureMetric] = None
    blood_oxygen: Optional[MetricStatusValue] = None
    sleep: Optional[MetricStatusValue] = None
    body_temperature: Optional[MetricStatusValue] = None
    activity: Optional[MetricStatusValue] = None


class HealthDataByDateResponse(BaseModel):
    device_id: int
    date: str
    health_score: int
    status: str
    metrics: HealthDataMetrics
