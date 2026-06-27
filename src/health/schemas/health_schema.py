from typing import Optional

from pydantic import BaseModel


# ── POST /health/upload ──────────────────────────────────────────────────────


class SleepRecordInput(BaseModel):
    date: str
    sleepQuality: int
    wakeCount: int
    deepSleepTime: int
    lowSleepTime: int
    allSleepTime: int
    sleepDown: str
    sleepUp: str
    sleepLine: Optional[str] = None


class BloodComponentData(BaseModel):
    uricAcid: Optional[float] = None
    tCHO: Optional[float] = None
    tAG: Optional[float] = None
    hDL: Optional[float] = None
    lDL: Optional[float] = None


class HealthRecordData(BaseModel):
    heartRate: Optional[float] = None
    bloodOxygen: Optional[float] = None
    respiratoryRate: Optional[float] = None
    sleepState: Optional[int] = None
    apneaResult: Optional[int] = None
    hypoxiaTime: Optional[int] = None
    cardiacLoad: Optional[float] = None
    isHypoxia: Optional[int] = None
    correct: Optional[int] = None
    bloodGlucose: Optional[float] = None
    sportStatus: Optional[int] = None
    bloodComponent: Optional[BloodComponentData] = None


class HealthRecordInput(BaseModel):
    date: str
    datetime: str
    data: HealthRecordData


class ActivityRecordData(BaseModel):
    sportValue: Optional[float] = None
    stepValue: Optional[int] = None
    wear: Optional[int] = None
    calValue: Optional[float] = None
    disValue: Optional[float] = None


class ActivityRecordInput(BaseModel):
    date: str
    datetime: str
    data: ActivityRecordData


class UploadHealthRequest(BaseModel):
    sleep_records: list[SleepRecordInput] = []
    health_records: list[HealthRecordInput] = []
    activity_records: list[ActivityRecordInput] = []
