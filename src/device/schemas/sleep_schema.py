from pydantic import BaseModel


class TimePoint(BaseModel):
    hour: int
    minute: int


class SleepUploadRequest(BaseModel):
    date: str
    sleepQuality: int | None = None
    wakeCount: int | None = None
    deepSleepTime: int | None = None
    lowSleepTime: int | None = None
    allSleepTime: int | None = None
    sleepLine: str | None = None
    sleepDown: TimePoint | None = None
    sleepUp: TimePoint | None = None


class SleepResponse(BaseModel):
    date: str
    sleepQuality: int | None = None
    wakeCount: int | None = None
    deepSleepTime: int | None = None
    lowSleepTime: int | None = None
    allSleepTime: int | None = None
    sleepLine: str | None = None
    sleepDown: TimePoint | None = None
    sleepUp: TimePoint | None = None
