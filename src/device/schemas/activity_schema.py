from pydantic import BaseModel


class ActivityRecordPayload(BaseModel):
    datetime: str
    sportValue: int | None = None
    sportStatus: int | None = None
    stepValue: int | None = None
    calValue: float | None = None
    disValue: float | None = None


class ActivityUploadRequest(BaseModel):
    id: int | None = None
    macAddress: str
    activityRecord: ActivityRecordPayload
