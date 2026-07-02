from pydantic import BaseModel


class SleepRecordPayload(BaseModel):
    segmentIndex: int | None = None
    startDateTime: str | None = None
    endDateTime: str | None = None
    sleepQuality: int | None = None
    wakeCount: int | None = None
    deepSleepTime: int | None = None
    lowSleepTime: int | None = None
    allSleepTime: int | None = None
    sleepLine: str | None = None


class SleepSummaryPayload(BaseModel):
    sleepQuality: int | None = None
    wakeCount: int | None = None
    deepSleepTime: int | None = None
    lowSleepTime: int | None = None
    allSleepTime: int | None = None
    segmentCount: int | None = None
    sleepDown: str | None = None
    sleepUp: str | None = None
    sleepLine: str | None = None


class SleepUploadRequest(BaseModel):
    id: int | None = None
    macAddress: str
    date: str
    sleepRecords: list[SleepRecordPayload]


class SleepDataResponse(BaseModel):
    id: int
    macAddress: str
    date: str
    sleepRecords: list[SleepRecordPayload]
    sleepSummary: SleepSummaryPayload | None = None
