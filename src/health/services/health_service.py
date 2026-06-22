from collections import defaultdict
from datetime import date as date_cls
from datetime import datetime, timezone

from sqlalchemy.orm import Session

from src.health.models.health_record_model import HealthRecord
from src.health.schemas.health_schema import (
    UploadHealthOriginRequest,
    UploadSleepRequest,
)
from src.health.services import health_metrics
from src.user_device.models.device_model import Device


def _batch_avg(values: list) -> float | None:
    clean = [v for v in values if v is not None]
    return round(sum(clean) / len(clean), 2) if clean else None


def upload_health_origin_data(db: Session, device: Device, body: UploadHealthOriginRequest) -> list[int]:
    by_date: dict[str, list] = defaultdict(list)
    for rec in body.records:
        by_date[rec.date].append(rec)

    record_ids = []
    for date_str in sorted(by_date):
        recs = by_date[date_str]
        record_date = date_cls.fromisoformat(date_str)
        record = (
            db.query(HealthRecord)
            .filter(HealthRecord.device_id == device.id, HealthRecord.date == record_date)
            .first()
        )
        if record is None:
            record = HealthRecord(
                device_id=device.id,
                date=record_date,
                recorded_at=datetime.now(timezone.utc),
            )
            db.add(record)

        # heart_rate: time-series, deduped by time
        new_hr = [{"time": r.time, "value": r.heartRate, "unit": "bpm"} for r in recs if r.heartRate is not None]
        if new_hr:
            existing = record.heart_rate or []
            seen = {e["time"] for e in existing}
            for reading in new_hr:
                if reading["time"] not in seen:
                    existing.append(reading)
                    seen.add(reading["time"])
            record.heart_rate = existing

        # met: time-series, deduped by time
        new_met = [{"time": r.time, "value": r.met, "unit": "MET"} for r in recs if r.met is not None]
        if new_met:
            existing = record.met or []
            seen = {e["time"] for e in existing}
            for entry in new_met:
                if entry["time"] not in seen:
                    existing.append(entry)
                    seen.add(entry["time"])
            record.met = existing

        # scalar fields: daily average from this batch
        bp_high = _batch_avg([r.bloodPressureHigh for r in recs])
        bp_low = _batch_avg([r.bloodPressureLow for r in recs])
        if bp_high is not None or bp_low is not None:
            record.blood_pressure = {"systolic": bp_high, "diastolic": bp_low, "unit": "mmHg"}

        spo2 = _batch_avg([r.bloodOxygen for r in recs])
        if spo2 is not None:
            record.blood_oxygen = {"value": spo2, "unit": "%"}

        temp = _batch_avg([r.bodyTemperature for r in recs])
        if temp is not None:
            record.body_temperature = {"value": temp, "unit": "°C"}

        hrv_val = _batch_avg([r.hrv for r in recs])
        if hrv_val is not None:
            record.hrv = {"value": hrv_val, "unit": "ms"}

        stress_val = _batch_avg([r.stress for r in recs])
        if stress_val is not None:
            record.stress = {"value": stress_val}

        # activity: sum of steps
        step_vals = [r.steps for r in recs if r.steps is not None]
        if step_vals:
            record.activity = {"steps": sum(step_vals)}

        # blood_components: average non-null values
        bc: dict[str, float] = {}
        for src, dst in (
            ("bloodGlucose", "blood_glucose"),
            ("uricAcid", "uric_acid"),
            ("totalCholesterol", "total_cholesterol"),
            ("triglyceride", "triglyceride"),
            ("hdl", "hdl"),
            ("ldl", "ldl"),
        ):
            avg = _batch_avg([getattr(r, src) for r in recs])
            if avg is not None:
                bc[dst] = avg
        if bc:
            record.blood_components = bc

        db.flush()
        record_ids.append(record.id)

    db.commit()
    return record_ids


def upload_sleep_data(db: Session, device: Device, body: UploadSleepRequest) -> int:
    record_date = date_cls.fromisoformat(body.date)
    record = (
        db.query(HealthRecord)
        .filter(HealthRecord.device_id == device.id, HealthRecord.date == record_date)
        .first()
    )

    if record is None:
        record = HealthRecord(
            device_id=device.id,
            date=record_date,
            recorded_at=datetime.now(timezone.utc),
        )
        db.add(record)

    record.sleep = {
        "start_time": body.time.start,
        "end_time": body.time.end,
        "light": body.value.light,
        "deep": body.value.deep,
        "wake": body.value.wakeCount,
        "total": body.value.total,
        "quality": body.value.quality,
        "raw": body.raw.model_dump() if body.raw else None,
    }

    db.commit()
    db.refresh(record)
    return record.id



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


