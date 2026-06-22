from typing import Literal, Optional

from pydantic import BaseModel


class SleepTimePayload(BaseModel):
    start: str
    end: str


class SleepValuePayload(BaseModel):
    light: Optional[int] = None
    deep: Optional[int] = None
    wakeCount: Optional[int] = None
    total: Optional[int] = None
    quality: Optional[int] = None


class SleepRawPayload(BaseModel):
    caliFlag: Optional[int] = None
    sleepLine: Optional[str] = None


class UploadSleepRequest(BaseModel):
    type: Literal["sleep"] = "sleep"
    date: str
    time: SleepTimePayload
    value: SleepValuePayload
    raw: Optional[SleepRawPayload] = None


class UploadHealthDataResponseData(BaseModel):
    health_record_id: str


class HealthOriginRecord(BaseModel):
    date: str
    time: str
    heartRate: Optional[float] = None
    bloodPressureHigh: Optional[float] = None
    bloodPressureLow: Optional[float] = None
    bloodOxygen: Optional[float] = None
    bodyTemperature: Optional[float] = None
    hrv: Optional[float] = None
    ecg: Optional[float] = None
    met: Optional[float] = None
    stress: Optional[float] = None
    steps: Optional[int] = None
    sportValue: Optional[float] = None
    gesture: Optional[int] = None
    ppg: Optional[float] = None
    ecgValue: Optional[float] = None
    respiratoryRate: Optional[float] = None
    sleepState: Optional[int] = None
    apneaResult: Optional[int] = None
    hypoxiaTime: Optional[int] = None
    cardiacLoad: Optional[float] = None
    isHypoxia: Optional[int] = None
    oxygenCorrect: Optional[int] = None
    bloodGlucose: Optional[float] = None
    uricAcid: Optional[float] = None
    totalCholesterol: Optional[float] = None
    triglyceride: Optional[float] = None
    hdl: Optional[float] = None
    ldl: Optional[float] = None
    sportStatusVersion: Optional[int] = None
    sportStatus: Optional[int] = None
    packageNumber: Optional[int] = None
    allPackage: Optional[int] = None


class UploadHealthOriginRequest(BaseModel):
    device_id: int
    intervalMinutes: int
    records: list[HealthOriginRecord]


class UploadHealthOriginResponseData(BaseModel):
    record_ids: list[int]


