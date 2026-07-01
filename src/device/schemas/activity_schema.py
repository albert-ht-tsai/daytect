from pydantic import BaseModel


class ActivityAvgRecordPayload(BaseModel):
    sportValue: int | None = None
    sportStatus: int | None = None
    stepValue: int | None = None
    calValue: float | None = None
    disValue: float | None = None


class ActivityUploadRequest(BaseModel):
    id: int | None = None
    macAddress: str
    date: str
    activityAvgRecord: ActivityAvgRecordPayload
