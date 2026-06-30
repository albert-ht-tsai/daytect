from pydantic import BaseModel


class BloodPressure(BaseModel):
    systolic: int | None = None
    diastolic: int | None = None


class BloodComponents(BaseModel):
    uricAcid: float | None = None
    tCHO: float | None = None
    tAG: float | None = None
    hDL: float | None = None
    lDL: float | None = None


class HealthEntry(BaseModel):
    datetime: str
    heartRate: int | None = None
    bloodPressure: BloodPressure | None = None
    bloodOxygen: int | None = None
    bodyTemperature: float | None = None
    hrv: int | None = None
    ecg: dict | None = None
    stress: int | None = None
    met: float | None = None
    bloodComponents: BloodComponents | None = None


class HealthUploadRequest(BaseModel):
    date: str
    data: list[HealthEntry]


class HealthResponse(BaseModel):
    date: str
    data: list[HealthEntry]
