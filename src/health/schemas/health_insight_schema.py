from pydantic import BaseModel


class HealthInsightMetrics(BaseModel):
    health_score: float | None = None
    health_score_label: str | None = None
    health_score_threshold: str | None = None

    heart_rate: float | None = None
    heart_rate_label: str | None = None
    heart_rate_threshold: str | None = None

    blood_pressure: str | None = None
    blood_pressure_label: str | None = None
    blood_pressure_threshold: str | None = None

    blood_oxygen: float | None = None
    blood_oxygen_label: str | None = None
    blood_oxygen_threshold: str | None = None

    body_temperature: float | None = None
    body_temperature_label: str | None = None
    body_temperature_threshold: str | None = None

    hrv: float | None = None
    hrv_label: str | None = None
    hrv_threshold: str | None = None

    res_rate: float | None = None
    res_rate_label: str | None = None
    res_rate_threshold: str | None = None

    pressure: float | None = None
    pressure_label: str | None = None
    pressure_threshold: str | None = None


class BaseHealthInsightResponse(BaseModel):
    session: int
    user: str
    start_date: str
    end_date: str
    metrics: HealthInsightMetrics
    summary: str
