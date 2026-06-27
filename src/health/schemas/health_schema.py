from typing import Optional

from pydantic import BaseModel


# ── POST /health/{device_id}/upload ─────────────────────────────────────────


class TimestampValue(BaseModel):
    datetime: str
    value: float


class HeartRateData(BaseModel):
    avg: Optional[float] = None
    min: Optional[float] = None
    max: Optional[float] = None
    values: Optional[list[TimestampValue]] = None


class BloodPressureValue(BaseModel):
    datetime: str
    systolic: float
    diastolic: float


class BloodPressureData(BaseModel):
    systolicAvg: Optional[float] = None
    diastolicAvg: Optional[float] = None
    values: Optional[list[BloodPressureValue]] = None


class BloodOxygenData(BaseModel):
    avg: Optional[float] = None
    min: Optional[float] = None
    max: Optional[float] = None
    values: Optional[list[TimestampValue]] = None


class BodyTemperatureData(BaseModel):
    avg: Optional[float] = None
    values: Optional[list[TimestampValue]] = None


class SkinTemperatureData(BaseModel):
    avg: Optional[float] = None
    values: Optional[list[TimestampValue]] = None


class ActivityValue(BaseModel):
    datetime: str
    steps: Optional[int] = None
    calories: Optional[float] = None
    distanceKm: Optional[float] = None
    sportValue: Optional[int] = None


class ActivityData(BaseModel):
    steps: Optional[int] = None
    calories: Optional[float] = None
    distanceKm: Optional[float] = None
    sportValue: Optional[int] = None
    values: Optional[list[ActivityValue]] = None


class RespiratoryRateData(BaseModel):
    avg: Optional[float] = None
    values: Optional[list[TimestampValue]] = None


class ApneaValue(BaseModel):
    datetime: str
    value: int


class ApneaData(BaseModel):
    apneaResults: Optional[list[ApneaValue]] = None
    hypoxiaTimes: Optional[list[ApneaValue]] = None
    isHypoxias: Optional[list[ApneaValue]] = None


class CardiacLoadData(BaseModel):
    values: Optional[list[TimestampValue]] = None


class SportStatusValue(BaseModel):
    datetime: str
    value: int


class SportStatusData(BaseModel):
    version: Optional[int] = None
    values: Optional[list[SportStatusValue]] = None


class BloodGlucoseData(BaseModel):
    value: Optional[float] = None
    datetime: Optional[str] = None


class BloodComponentData(BaseModel):
    datetime: Optional[str] = None
    uricAcid: Optional[float] = None
    tCHO: Optional[float] = None
    tAG: Optional[float] = None
    hDL: Optional[float] = None
    lDL: Optional[float] = None


class HealthRecordBlock(BaseModel):
    heartRate: Optional[HeartRateData] = None
    bloodPressure: Optional[BloodPressureData] = None
    bloodOxygen: Optional[BloodOxygenData] = None
    bodyTemperature: Optional[BodyTemperatureData] = None
    skinTemperature: Optional[SkinTemperatureData] = None
    activity: Optional[ActivityData] = None
    respiratoryRate: Optional[RespiratoryRateData] = None
    apnea: Optional[ApneaData] = None
    cardiacLoad: Optional[CardiacLoadData] = None
    sportStatus: Optional[SportStatusData] = None
    bloodGlucose: Optional[BloodGlucoseData] = None
    bloodComponent: Optional[BloodComponentData] = None


class SleepRecordData(BaseModel):
    date: Optional[str] = None
    sleepQuality: Optional[int] = None
    wakeCount: Optional[int] = None
    deepSleepTime: Optional[int] = None
    lowSleepTime: Optional[int] = None
    allSleepTime: Optional[int] = None
    sleepDown: Optional[str] = None
    sleepUp: Optional[str] = None
    sleepLine: Optional[str] = None


class UploadHealthRequest(BaseModel):
    date: str
    sleep_records: Optional[SleepRecordData] = None
    health_records: list[HealthRecordBlock] = []


class UploadHealthResponse(BaseModel):
    success: bool = True
    message: str = "Health data uploaded successfully."



