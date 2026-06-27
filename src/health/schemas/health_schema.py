from typing import Optional

from pydantic import BaseModel


# ── POST /health/upload ──────────────────────────────────────────────────────


class RawSleepDataInput(BaseModel):
    sleep_date: Optional[str] = None
    cali_flag: Optional[int] = None
    sleep_quality: Optional[int] = None
    wake_count: Optional[int] = None
    deep_sleep_minutes: Optional[int] = None
    light_sleep_minutes: Optional[int] = None
    total_sleep_minutes: Optional[int] = None
    sleep_start: Optional[str] = None
    sleep_end: Optional[str] = None
    sleep_line: Optional[str] = None
    sleep_line_type: Optional[str] = None


class RawActivityValue(BaseModel):
    device_time: str
    step_value: Optional[int] = None
    sport_value: Optional[int] = None
    calories: Optional[float] = None
    distance_km: Optional[float] = None


class RawActivityInput(BaseModel):
    values: list[RawActivityValue] = []


class HeartRateInput(BaseModel):
    value: Optional[int] = None
    ppg_values: Optional[list[int]] = None
    ecg_values: Optional[list[int]] = None
    ppg_count: Optional[int] = None
    ecg_count: Optional[int] = None


class BloodPressureInput(BaseModel):
    systolic: Optional[int] = None
    diastolic: Optional[int] = None
    pressure: Optional[int] = None


class BloodOxygenInput(BaseModel):
    values: Optional[list[int]] = None
    valid_count: Optional[int] = None
    correct_values: Optional[list[int]] = None


class RespiratoryRateInput(BaseModel):
    values: Optional[list[int]] = None
    valid_count: Optional[int] = None


class BodyTemperatureInput(BaseModel):
    temperature: Optional[float] = None
    base_temperature: Optional[float] = None


class SleepStateInput(BaseModel):
    values: Optional[list[int]] = None
    valid_count: Optional[int] = None


class ApneaInput(BaseModel):
    apnea_results: Optional[list] = None
    hypoxia_times: Optional[list] = None
    is_hypoxias: Optional[list] = None


class CardiacLoadInput(BaseModel):
    values: Optional[list] = None


class BloodComponentInput(BaseModel):
    uric_acid: Optional[float] = None
    total_cholesterol: Optional[float] = None
    triglyceride: Optional[float] = None
    hdl: Optional[float] = None
    ldl: Optional[float] = None


class SportStatusInput(BaseModel):
    version: Optional[int] = None
    values: Optional[list[int]] = None


class RawHealthRecordInput(BaseModel):
    device_time: str
    heart_rate: Optional[HeartRateInput] = None
    blood_pressure: Optional[BloodPressureInput] = None
    blood_oxygen: Optional[BloodOxygenInput] = None
    respiratory_rate: Optional[RespiratoryRateInput] = None
    body_temperature: Optional[BodyTemperatureInput] = None
    sleep_state: Optional[SleepStateInput] = None
    apnea: Optional[ApneaInput] = None
    cardiac_load: Optional[CardiacLoadInput] = None
    blood_glucose: Optional[float] = None
    blood_component: Optional[BloodComponentInput] = None
    sport_status: Optional[SportStatusInput] = None
    met: Optional[float] = None


class UploadHealthRequest(BaseModel):
    mac_address: str
    raw_sleep_data: Optional[RawSleepDataInput] = None
    raw_activity: Optional[RawActivityInput] = None
    raw_health_records: list[RawHealthRecordInput] = []
