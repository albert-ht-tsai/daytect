from datetime import date as date_cls
from datetime import time as time_cls
from datetime import datetime, timedelta, timezone

from sqlalchemy.orm import Session

from src.health.models.health_record_model import HealthRecord
from src.health.models.raw_health_record_model import RawHealthRecord
from src.health.models.raw_activity_model import RawActivity
from src.health.models.raw_sleep_data_model import RawSleepData
from src.health.schemas.health_schema import UploadHealthRequest
from src.health.services import health_rules


# ── POST /health/upload ──────────────────────────────────────────────────────

# Fields where 0 is treated as invalid (convert to null, do not overwrite DB)
_BP_ZERO_INVALID = frozenset({"systolic", "diastolic"})
_BT_ZERO_INVALID = frozenset({"temperature", "base_temperature"})


def _parse_device_time(dt_str: str) -> datetime | None:
    try:
        return datetime.strptime(dt_str, "%Y-%m-%d %H:%M:%S")
    except (ValueError, TypeError):
        return None


def _is_valid_device_time(dt: datetime, now: datetime) -> bool:
    return (now - timedelta(days=30)) <= dt <= (now + timedelta(minutes=10))


def _merge_sub_model(acc_val: dict | None, model, zero_invalid: frozenset = frozenset()) -> dict | None:
    """Merge a Pydantic sub-model into an accumulated dict.

    - None fields (excluded via exclude_none) → keep existing value
    - Empty arrays → keep existing value
    - 0 in zero_invalid fields → keep existing value (treat as null)
    """
    if model is None:
        return acc_val
    incoming = model.model_dump(exclude_none=True)
    if not incoming:
        return acc_val
    if acc_val is None:
        result: dict = {}
        for k, v in incoming.items():
            result[k] = (None if (k in zero_invalid and v == 0) else v)
        return result
    result = dict(acc_val)
    for k, v in incoming.items():
        if isinstance(v, list) and len(v) == 0:
            continue
        if k in zero_invalid and v == 0:
            continue
        result[k] = v
    return result


def _accumulate_health_record(acc: dict, rec) -> dict:
    """Pre-merge a health record entry into an accumulated dict (within-payload dedup)."""
    merged = dict(acc)
    for field, zero_inv in (
        ("heart_rate", frozenset()),
        ("blood_pressure", _BP_ZERO_INVALID),
        ("blood_oxygen", frozenset()),
        ("respiratory_rate", frozenset()),
        ("body_temperature", _BT_ZERO_INVALID),
        ("sleep_state", frozenset()),
        ("apnea", frozenset()),
        ("cardiac_load", frozenset()),
        ("blood_component", frozenset()),
        ("sport_status", frozenset()),
    ):
        merged[field] = _merge_sub_model(acc.get(field), getattr(rec, field), zero_inv)
    # blood_glucose: 0 is invalid
    if rec.blood_glucose is not None and rec.blood_glucose != 0:
        merged["blood_glucose"] = rec.blood_glucose
    # met: 0 is treated as valid (resting MET)
    if rec.met is not None:
        merged["met"] = rec.met
    return merged


def _db_merge_json(existing_val: dict | None, incoming_val: dict | None) -> dict | None:
    """Merge a payload dict (already zero-invalid cleaned) into an existing DB JSON column.

    - None incoming → keep existing
    - Empty arrays in incoming → keep existing
    - Any other value → overwrite
    """
    if incoming_val is None:
        return existing_val
    if existing_val is None:
        return incoming_val
    result = dict(existing_val)
    for k, v in incoming_val.items():
        if v is None:
            continue
        if isinstance(v, list) and len(v) == 0:
            continue
        result[k] = v
    return result


def upload_health(db: Session, user_id: int, body: UploadHealthRequest) -> dict:
    mac = body.mac_address
    now = datetime.now(timezone.utc).replace(tzinfo=None)  # naive for device_time comparison
    stats = {
        "raw_health_inserted": 0,
        "raw_health_updated": 0,
        "activity_inserted": 0,
        "activity_updated": 0,
        "sleep_inserted": 0,
        "sleep_updated": 0,
    }
    affected_dates: set[str] = set()

    # ── 1. raw_sleep_data ──────────────────────────────────────────────────
    if body.raw_sleep_data:
        s = body.raw_sleep_data
        if s.sleep_date:
            sleep_dt = date_cls.fromisoformat(s.sleep_date)
            affected_dates.add(s.sleep_date)
            existing_sleep = (
                db.query(RawSleepData)
                .filter(
                    RawSleepData.user_id == user_id,
                    RawSleepData.mac_address == mac,
                    RawSleepData.sleep_date == sleep_dt,
                )
                .first()
            )
            if existing_sleep is None:
                db.add(RawSleepData(
                    user_id=user_id,
                    mac_address=mac,
                    sleep_date=sleep_dt,
                    cali_flag=s.cali_flag,
                    sleep_quality=s.sleep_quality,
                    wake_count=s.wake_count,
                    deep_sleep_minutes=s.deep_sleep_minutes,
                    light_sleep_minutes=s.light_sleep_minutes,
                    total_sleep_minutes=s.total_sleep_minutes,
                    sleep_start=s.sleep_start,
                    sleep_end=s.sleep_end,
                    sleep_line=s.sleep_line,
                    sleep_line_type=s.sleep_line_type,
                ))
                stats["sleep_inserted"] = 1
            else:
                for field, val in (
                    ("cali_flag", s.cali_flag),
                    ("sleep_quality", s.sleep_quality),
                    ("wake_count", s.wake_count),
                    ("deep_sleep_minutes", s.deep_sleep_minutes),
                    ("light_sleep_minutes", s.light_sleep_minutes),
                    ("total_sleep_minutes", s.total_sleep_minutes),
                    ("sleep_start", s.sleep_start),
                    ("sleep_end", s.sleep_end),
                    ("sleep_line", s.sleep_line),
                    ("sleep_line_type", s.sleep_line_type),
                ):
                    if val is not None:
                        setattr(existing_sleep, field, val)
                existing_sleep.updated_at = datetime.now(timezone.utc)
                stats["sleep_updated"] = 1

    # ── 2. raw_activity ────────────────────────────────────────────────────
    if body.raw_activity and body.raw_activity.values:
        # Pre-merge same device_time within payload (last non-null value wins per field)
        activity_map: dict[str, tuple[datetime, dict]] = {}
        for act in body.raw_activity.values:
            dt = _parse_device_time(act.device_time)
            if dt is None or not _is_valid_device_time(dt, now):
                continue
            key = act.device_time
            if key not in activity_map:
                activity_map[key] = (dt, {
                    "step_value": act.step_value,
                    "sport_value": act.sport_value,
                    "calories": act.calories,
                    "distance_km": act.distance_km,
                })
            else:
                _, acc = activity_map[key]
                if act.step_value is not None:
                    acc["step_value"] = act.step_value
                if act.sport_value is not None:
                    acc["sport_value"] = act.sport_value
                if act.calories is not None:
                    acc["calories"] = act.calories
                if act.distance_km is not None:
                    acc["distance_km"] = act.distance_km

        for key, (dt, data) in activity_map.items():
            affected_dates.add(dt.strftime("%Y-%m-%d"))
            existing_act = (
                db.query(RawActivity)
                .filter(
                    RawActivity.user_id == user_id,
                    RawActivity.mac_address == mac,
                    RawActivity.device_time == dt,
                )
                .first()
            )
            if existing_act is None:
                db.add(RawActivity(
                    user_id=user_id,
                    mac_address=mac,
                    device_time=dt,
                    step_value=data.get("step_value"),
                    sport_value=data.get("sport_value"),
                    calories=data.get("calories"),
                    distance_km=data.get("distance_km"),
                ))
                stats["activity_inserted"] += 1
            else:
                for field in ("step_value", "sport_value", "calories", "distance_km"):
                    val = data.get(field)
                    if val is not None:
                        setattr(existing_act, field, val)
                existing_act.updated_at = datetime.now(timezone.utc)
                stats["activity_updated"] += 1

    # ── 3. raw_health_records ──────────────────────────────────────────────
    if body.raw_health_records:
        # Pre-merge same device_time within payload
        health_map: dict[str, tuple[datetime, dict]] = {}
        for rec in body.raw_health_records:
            dt = _parse_device_time(rec.device_time)
            if dt is None or not _is_valid_device_time(dt, now):
                continue
            key = rec.device_time
            if key not in health_map:
                health_map[key] = (dt, _accumulate_health_record({}, rec))
            else:
                _, acc = health_map[key]
                health_map[key] = (dt, _accumulate_health_record(acc, rec))

        _JSON_FIELDS = (
            "heart_rate", "blood_pressure", "blood_oxygen", "respiratory_rate",
            "body_temperature", "sleep_state", "apnea", "cardiac_load",
            "blood_component", "sport_status",
        )

        for key, (dt, data) in health_map.items():
            affected_dates.add(dt.strftime("%Y-%m-%d"))
            existing_hr = (
                db.query(RawHealthRecord)
                .filter(
                    RawHealthRecord.user_id == user_id,
                    RawHealthRecord.mac_address == mac,
                    RawHealthRecord.device_time == dt,
                )
                .first()
            )
            if existing_hr is None:
                db.add(RawHealthRecord(
                    user_id=user_id,
                    mac_address=mac,
                    device_time=dt,
                    heart_rate=data.get("heart_rate"),
                    blood_pressure=data.get("blood_pressure"),
                    blood_oxygen=data.get("blood_oxygen"),
                    respiratory_rate=data.get("respiratory_rate"),
                    body_temperature=data.get("body_temperature"),
                    sleep_state=data.get("sleep_state"),
                    apnea=data.get("apnea"),
                    cardiac_load=data.get("cardiac_load"),
                    blood_glucose=data.get("blood_glucose"),
                    blood_component=data.get("blood_component"),
                    sport_status=data.get("sport_status"),
                    met=data.get("met"),
                ))
                stats["raw_health_inserted"] += 1
            else:
                for field in _JSON_FIELDS:
                    incoming_val = data.get(field)
                    if incoming_val is not None:
                        setattr(existing_hr, field, _db_merge_json(getattr(existing_hr, field), incoming_val))
                if data.get("blood_glucose") is not None:
                    existing_hr.blood_glucose = data["blood_glucose"]
                if data.get("met") is not None:
                    existing_hr.met = data["met"]
                existing_hr.updated_at = datetime.now(timezone.utc)
                stats["raw_health_updated"] += 1

    db.commit()

    return {
        "mac_address": mac,
        "received": {
            "raw_health_records": len(body.raw_health_records),
            "raw_activity_values": len(body.raw_activity.values) if body.raw_activity else 0,
            "raw_sleep_data": 1 if body.raw_sleep_data else 0,
        },
        "merged": stats,
        "affected_dates": sorted(affected_dates),
        "summary_rebuilt": False,
    }


# ── Shared windowed metric extraction (used by health_summary_service) ───────


def _avg(values: list[float]) -> float | None:
    clean = [v for v in values if v is not None]
    return round(sum(clean) / len(clean), 2) if clean else None


def _diff(current: float | None, previous: float | None) -> float | None:
    if current is None or previous is None:
        return None
    return round(current - previous, 2)


def _extract_time_of_day(dt_str: str) -> time_cls | None:
    try:
        return datetime.strptime(dt_str, "%Y-%m-%d %H:%M:%S").time()
    except (ValueError, TypeError):
        return None


def _in_window(dt_str: str, start: time_cls, end: time_cls) -> bool:
    t = _extract_time_of_day(dt_str)
    if t is None:
        return True
    if start <= end:
        return start <= t <= end
    return t >= start or t <= end


def _filter_values(values: list[dict] | None, start: time_cls, end: time_cls) -> list[dict]:
    return [v for v in (values or []) if _in_window(v.get("datetime", ""), start, end)]


def _windowed_avg_min_max(metric: dict, start: time_cls, end: time_cls) -> dict:
    values = metric.get("values") or []
    if values:
        nums = [v["value"] for v in _filter_values(values, start, end)]
        return {"avg": _avg(nums), "min": min(nums) if nums else None, "max": max(nums) if nums else None}
    return {"avg": metric.get("avg"), "min": metric.get("min"), "max": metric.get("max")}


def _windowed_avg(metric: dict, start: time_cls, end: time_cls) -> float | None:
    values = metric.get("values") or []
    if values:
        nums = [v["value"] for v in _filter_values(values, start, end)]
        return _avg(nums)
    return metric.get("avg")


def _windowed_blood_pressure(metric: dict, start: time_cls, end: time_cls) -> dict:
    values = metric.get("values") or []
    if values:
        filtered = _filter_values(values, start, end)
        return {
            "systolicAvg": _avg([v["systolic"] for v in filtered]),
            "diastolicAvg": _avg([v["diastolic"] for v in filtered]),
        }
    return {"systolicAvg": metric.get("systolicAvg"), "diastolicAvg": metric.get("diastolicAvg")}


def _windowed_activity(metric: dict, start: time_cls, end: time_cls) -> dict:
    values = metric.get("values") or []
    if values:
        filtered = _filter_values(values, start, end)
        if not filtered:
            return {"steps": None, "calories": None, "distanceKm": None, "sportValue": None}
        return {
            "steps": sum(v.get("steps") or 0 for v in filtered),
            "calories": round(sum(v.get("calories") or 0.0 for v in filtered), 2),
            "distanceKm": round(sum(v.get("distanceKm") or 0.0 for v in filtered), 3),
            "sportValue": sum(v.get("sportValue") or 0 for v in filtered),
        }
    return {
        "steps": metric.get("steps"),
        "calories": metric.get("calories"),
        "distanceKm": metric.get("distanceKm"),
        "sportValue": metric.get("sportValue"),
    }


def _sleep_values(record: HealthRecord | None) -> dict:
    s = (record.sleep if record else None) or {}
    return {
        "sleepQuality": s.get("sleepQuality"),
        "allSleepTime": s.get("allSleepTime"),
        "deepSleepTime": s.get("deepSleepTime"),
        "wakeCount": s.get("wakeCount"),
    }


def _day_metrics(record: HealthRecord | None, start: time_cls, end: time_cls) -> dict:
    return {
        "heartRate": _windowed_avg_min_max(record.heart_rate or {} if record else {}, start, end),
        "bloodPressure": _windowed_blood_pressure(record.blood_pressure or {} if record else {}, start, end),
        "bloodOxygen": _windowed_avg_min_max(record.blood_oxygen or {} if record else {}, start, end),
        "bodyTemperature": {"avg": _windowed_avg(record.body_temperature or {} if record else {}, start, end)},
        "skinTemperature": {"avg": _windowed_avg(record.skin_temperature or {} if record else {}, start, end)},
        "sleep": _sleep_values(record),
        "activity": _windowed_activity(record.activity or {} if record else {}, start, end),
        "respiratoryRate": {"avg": _windowed_avg(record.respiratory_rate or {} if record else {}, start, end)},
        "cardiacLoad": {"avg": _windowed_avg(record.cardiac_load or {} if record else {}, start, end)},
    }


def _build_metrics(current: dict, previous: dict) -> tuple[dict, list[str]]:
    hr_status = health_rules.heart_rate_status(current["heartRate"]["avg"], previous["heartRate"]["avg"])
    bo_status = health_rules.blood_oxygen_status(current["bloodOxygen"]["avg"], previous["bloodOxygen"]["avg"])
    bt_status = health_rules.body_temperature_status(current["bodyTemperature"]["avg"], previous["bodyTemperature"]["avg"])
    st_status = health_rules.skin_temperature_status(current["skinTemperature"]["avg"], previous["skinTemperature"]["avg"])
    rr_status = health_rules.respiratory_rate_status(current["respiratoryRate"]["avg"], previous["respiratoryRate"]["avg"])
    cl_status = health_rules.cardiac_load_status(current["cardiacLoad"]["avg"], previous["cardiacLoad"]["avg"])
    bp_status = health_rules.blood_pressure_status(
        current["bloodPressure"]["systolicAvg"],
        current["bloodPressure"]["diastolicAvg"],
        previous["bloodPressure"]["systolicAvg"],
        previous["bloodPressure"]["diastolicAvg"],
    )
    sleep_status = health_rules.sleep_status(current["sleep"], previous["sleep"])
    activity_status = health_rules.activity_status(current["activity"], previous["activity"])

    metrics = {
        "heartRate": {
            "current": current["heartRate"]["avg"],
            "previous": previous["heartRate"]["avg"],
            "unit": "bpm",
            "change": _diff(current["heartRate"]["avg"], previous["heartRate"]["avg"]),
            "change_percent": health_rules.percent_change(current["heartRate"]["avg"], previous["heartRate"]["avg"]),
            "status": hr_status,
        },
        "bloodPressure": {
            "current": current["bloodPressure"],
            "previous": previous["bloodPressure"],
            "unit": "mmHg",
            "change": {
                "systolicAvg": _diff(current["bloodPressure"]["systolicAvg"], previous["bloodPressure"]["systolicAvg"]),
                "diastolicAvg": _diff(
                    current["bloodPressure"]["diastolicAvg"], previous["bloodPressure"]["diastolicAvg"]
                ),
            },
            "status": bp_status,
        },
        "bloodOxygen": {
            "current": current["bloodOxygen"]["avg"],
            "previous": previous["bloodOxygen"]["avg"],
            "unit": "%",
            "change": _diff(current["bloodOxygen"]["avg"], previous["bloodOxygen"]["avg"]),
            "change_percent": health_rules.percent_change(current["bloodOxygen"]["avg"], previous["bloodOxygen"]["avg"]),
            "status": bo_status,
        },
        "bodyTemperature": {
            "current": current["bodyTemperature"]["avg"],
            "previous": previous["bodyTemperature"]["avg"],
            "unit": "°C",
            "change": _diff(current["bodyTemperature"]["avg"], previous["bodyTemperature"]["avg"]),
            "status": bt_status,
        },
        "skinTemperature": {
            "current": current["skinTemperature"]["avg"],
            "previous": previous["skinTemperature"]["avg"],
            "unit": "°C",
            "change": _diff(current["skinTemperature"]["avg"], previous["skinTemperature"]["avg"]),
            "status": st_status,
        },
        "sleep": {
            "current": current["sleep"],
            "previous": previous["sleep"],
            "unit": "minute",
            "status": sleep_status,
        },
        "activity": {
            "current": current["activity"],
            "previous": previous["activity"],
            "status": activity_status,
        },
        "respiratoryRate": {
            "current": current["respiratoryRate"]["avg"],
            "previous": previous["respiratoryRate"]["avg"],
            "unit": "times/min",
            "change": _diff(current["respiratoryRate"]["avg"], previous["respiratoryRate"]["avg"]),
            "status": rr_status,
        },
        "cardiacLoad": {
            "current": current["cardiacLoad"]["avg"],
            "previous": previous["cardiacLoad"]["avg"],
            "change": _diff(current["cardiacLoad"]["avg"], previous["cardiacLoad"]["avg"]),
            "status": cl_status,
        },
    }

    statuses = [hr_status, bp_status, bo_status, bt_status, st_status, sleep_status, activity_status, rr_status, cl_status]
    return metrics, statuses


def _summary(statuses: list[str]) -> dict:
    return {
        "improve_count": statuses.count("improve"),
        "stable_count": statuses.count("stable"),
        "decrease_count": statuses.count("decrease"),
    }


# ── GET /health/daily (used by report pipeline) ──────────────────────────────


def get_daily_status(
    db: Session, user_id: int, date_str: str, start_time_str: str, end_time_str: str
) -> dict | None:
    record_date = date_cls.fromisoformat(date_str)
    compare_date = record_date - timedelta(days=1)
    start_t = time_cls.fromisoformat(start_time_str)
    end_t = time_cls.fromisoformat(end_time_str)

    record = (
        db.query(HealthRecord)
        .filter(HealthRecord.user_id == user_id, HealthRecord.date == record_date)
        .first()
    )
    if record is None:
        return None

    previous_record = (
        db.query(HealthRecord)
        .filter(HealthRecord.user_id == user_id, HealthRecord.date == compare_date)
        .first()
    )

    current = _day_metrics(record, start_t, end_t)
    previous = _day_metrics(previous_record, start_t, end_t)
    metrics, statuses = _build_metrics(current, previous)

    return {
        "user_id": user_id,
        "date": record_date.isoformat(),
        "compare_date": compare_date.isoformat(),
        "period": {"start_time": start_time_str, "end_time": end_time_str},
        "overall_status": health_rules.majority_status(statuses),
        "summary": _summary(statuses),
        "metrics": metrics,
    }
