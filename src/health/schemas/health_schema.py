from typing import Optional

from pydantic import BaseModel


class SleepRecord(BaseModel):
    date: str
    startTime: str
    endTime: str
    sleepQuality: Optional[int] = None
    wakeCount: Optional[int] = None
    deepSleepTime: Optional[int] = None
    lightSleepTime: Optional[int] = None
    totalSleepTime: Optional[int] = None
    caliFlag: Optional[int] = None
    sleepLine: Optional[str] = None


class UploadSleepRequest(BaseModel):
    records: list[SleepRecord]


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
    intervalMinutes: int
    records: list[HealthOriginRecord]
