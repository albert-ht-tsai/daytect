from pydantic import BaseModel


class HeartRate(BaseModel):
    ppgs: int | None = None
    unit: str | None = None


class BloodPressure(BaseModel):
    systolic: int | None = None
    diastolic: int | None = None
    unit: str | None = None


class BloodOxygen(BaseModel):
    oxygens: int | None = None
    unit: str | None = None


class BodyTemperature(BaseModel):
    temperature: float | None = None
    baseTemperature: float | None = None
    unit: str | None = None


class Respiratory(BaseModel):
    resRates: int | None = None
    unit: str | None = None


class Hrv(BaseModel):
    values: int | None = None
    unit: str | None = None


class Ecg(BaseModel):
    values: int | None = None


class Stress(BaseModel):
    pressure: int | None = None


class Met(BaseModel):
    values: int | None = None


class BloodComponents(BaseModel):
    uricAcid: float | None = None
    tCHO: float | None = None
    tAG: float | None = None
    hDL: float | None = None
    lDL: float | None = None


class HealthRecordPayload(BaseModel):
    datetime: str
    heartRate: HeartRate | None = None
    bloodPressure: BloodPressure | None = None
    bloodOxygen: BloodOxygen | None = None
    bodyTemperature: BodyTemperature | None = None
    respiratory: Respiratory | None = None
    hrv: Hrv | None = None
    ecg: Ecg | None = None
    stress: Stress | None = None
    met: Met | None = None
    bloodComponents: BloodComponents | None = None
    apneaResults: int | None = None
    hypoxiaTimes: int | None = None
    cardiacLoads: int | None = None
    isHypoxias: int | None = None
    bloodGlucose: int | None = None


class HealthUploadRequest(BaseModel):
    id: int | None = None
    macAddress: str
    healthRecord: HealthRecordPayload
