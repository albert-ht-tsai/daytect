from sqlalchemy.orm import Session

from src.health.models.health_record_model import HealthRecord
from src.health.schemas.health_schema import (
    BloodPressureMetric,
    HealthDataByDateResponse,
    HealthDataMetrics,
    MetricStatusValue,
    UploadHealthDataRequest,
)
from src.health.services import health_metrics
from src.user_device.models.device_model import Device


def upload_health_data(db: Session, device: Device, body: UploadHealthDataRequest) -> int:
    record_date = body.recorded_at.date()
    record = (
        db.query(HealthRecord)
        .filter(HealthRecord.device_id == device.id, HealthRecord.date == record_date)
        .first()
    )

    if record is None:
        record = HealthRecord(device_id=device.id, date=record_date, recorded_at=body.recorded_at)
        db.add(record)
    else:
        record.recorded_at = body.recorded_at

    if body.heart_rate is not None:
        new_readings = [r.model_dump(mode="json") for r in body.heart_rate]
        existing = record.heart_rate or []
        seen_times = {r["time"] for r in existing}
        for reading in new_readings:
            if reading["time"] not in seen_times:
                existing.append(reading)
                seen_times.add(reading["time"])
        record.heart_rate = existing

    for field in (
        "sleep",
        "blood_pressure",
        "blood_oxygen",
        "body_temperature",
        "hrv",
        "ecg",
        "stress",
        "activity",
        "blood_components",
    ):
        value = getattr(body, field)
        if value is not None:
            setattr(record, field, value if isinstance(value, dict) else value.model_dump(mode="json"))

    db.commit()
    db.refresh(record)
    return record.id


def get_available_dates(db: Session, device: Device) -> list[str]:
    rows = (
        db.query(HealthRecord.date)
        .filter(HealthRecord.device_id == device.id)
        .order_by(HealthRecord.date.desc())
        .all()
    )
    return [row[0].isoformat() for row in rows]


def average_heart_rate(record: HealthRecord) -> float | None:
    readings = record.heart_rate or []
    if not readings:
        return None
    return round(sum(r["value"] for r in readings) / len(readings), 1)


def compute_metric_statuses(record: HealthRecord) -> dict:
    hr = average_heart_rate(record)
    hrv_value = (record.hrv or {}).get("value")
    bp = record.blood_pressure or {}
    spo2 = (record.blood_oxygen or {}).get("value")
    temp = (record.body_temperature or {}).get("value")
    sleep_total = (record.sleep or {}).get("total")
    steps = (record.activity or {}).get("steps")

    return {
        "heart_rate": health_metrics.heart_rate_status(hr),
        "hrv": health_metrics.hrv_status(hrv_value),
        "blood_pressure": health_metrics.blood_pressure_status(bp.get("systolic"), bp.get("diastolic")),
        "blood_oxygen": health_metrics.blood_oxygen_status(spo2),
        "sleep": health_metrics.sleep_status(sleep_total),
        "body_temperature": health_metrics.body_temperature_status(temp),
        "activity": health_metrics.activity_status(steps),
    }


def get_health_data_by_date(db: Session, device: Device, date) -> HealthDataByDateResponse | None:
    record = (
        db.query(HealthRecord)
        .filter(HealthRecord.device_id == device.id, HealthRecord.date == date)
        .first()
    )
    if record is None:
        return None

    statuses = compute_metric_statuses(record)
    score, level = health_metrics.compute_health_score(statuses)

    sleep = record.sleep or {}
    activity = record.activity or {}
    bp = record.blood_pressure or {}

    sleep_total = sleep.get("total")
    sleep_label = f"{int(sleep_total // 60)}h {int(sleep_total % 60)}m" if sleep_total else None

    metrics = HealthDataMetrics(
        heart_rate=MetricStatusValue(value=average_heart_rate(record), unit="bpm", status=statuses["heart_rate"]),
        hrv=MetricStatusValue(value=(record.hrv or {}).get("value"), unit="ms", status=statuses["hrv"]),
        blood_pressure=BloodPressureMetric(
            systolic=bp.get("systolic"),
            diastolic=bp.get("diastolic"),
            unit=bp.get("unit", "mmHg"),
            status=statuses["blood_pressure"],
        ),
        blood_oxygen=MetricStatusValue(
            value=(record.blood_oxygen or {}).get("value"), unit="%", status=statuses["blood_oxygen"]
        ),
        sleep=MetricStatusValue(value=sleep_label, status=statuses["sleep"]),
        body_temperature=MetricStatusValue(
            value=(record.body_temperature or {}).get("value"), unit="celsius", status=statuses["body_temperature"]
        ),
        activity=MetricStatusValue(value=activity.get("steps"), status=statuses["activity"]),
    )

    return HealthDataByDateResponse(
        device_id=device.id,
        date=record.date.isoformat(),
        health_score=score,
        status=level,
        metrics=metrics,
    )
