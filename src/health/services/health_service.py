from datetime import date as date_cls
from datetime import time as time_cls
from datetime import datetime, timedelta

from sqlalchemy.orm import Session

from src.device.models.device_model import Device
from src.health.models.health_record_model import HealthRecord
from src.health.schemas.health_schema import UploadHealthRequest
from src.health.services import health_rules


def _avg(values: list[float]) -> float | None:
    clean = [v for v in values if v is not None]
    return round(sum(clean) / len(clean), 2) if clean else None


def _diff(current: float | None, previous: float | None) -> float | None:
    if current is None or previous is None:
        return None
    return round(current - previous, 2)


# ── POST /health/{device_id}/upload ─────────────────────────────────────────


def upload_health(db: Session, device: Device, body: UploadHealthRequest) -> None:
    record_date = date_cls.fromisoformat(body.date)
    record = (
        db.query(HealthRecord)
        .filter(HealthRecord.device_id == device.id, HealthRecord.date == record_date)
        .first()
    )
    if record is None:
        record = HealthRecord(device_id=device.id, date=record_date)
        db.add(record)

    if body.sleep_records:
        s = body.sleep_records
        record.sleep = {
            "date": s.date or body.date,
            "sleepQuality": s.sleepQuality,
            "wakeCount": s.wakeCount,
            "deepSleepTime": s.deepSleepTime,
            "lowSleepTime": s.lowSleepTime,
            "allSleepTime": s.allSleepTime,
            "sleepDown": s.sleepDown,
            "sleepUp": s.sleepUp,
            "sleepLine": s.sleepLine,
        }

    hr_values: list[dict] = []
    bp_values: list[dict] = []
    bo_values: list[dict] = []
    bt_values: list[dict] = []
    st_values: list[dict] = []
    rr_values: list[dict] = []
    apnea_results: list[dict] = []
    hypoxia_times: list[dict] = []
    is_hypoxias: list[dict] = []
    cl_values: list[dict] = []
    sport_status_values: list[dict] = []
    sport_status_version: int | None = None
    activity_values: list[dict] = []
    total_steps = 0
    total_calories = 0.0
    total_distance = 0.0
    total_sport_value = 0
    has_activity = False
    blood_glucose: dict | None = None
    blood_component: dict | None = None

    for block in body.health_records:
        if block.heartRate and block.heartRate.values:
            hr_values += [{"datetime": v.datetime, "value": v.value} for v in block.heartRate.values]

        if block.bloodPressure and block.bloodPressure.values:
            bp_values += [
                {"datetime": v.datetime, "systolic": v.systolic, "diastolic": v.diastolic}
                for v in block.bloodPressure.values
            ]

        if block.bloodOxygen and block.bloodOxygen.values:
            bo_values += [{"datetime": v.datetime, "value": v.value} for v in block.bloodOxygen.values]

        if block.bodyTemperature and block.bodyTemperature.values:
            bt_values += [{"datetime": v.datetime, "value": v.value} for v in block.bodyTemperature.values]

        if block.skinTemperature and block.skinTemperature.values:
            st_values += [{"datetime": v.datetime, "value": v.value} for v in block.skinTemperature.values]

        if block.activity:
            has_activity = True
            total_steps += block.activity.steps or 0
            total_calories += block.activity.calories or 0.0
            total_distance += block.activity.distanceKm or 0.0
            total_sport_value += block.activity.sportValue or 0
            if block.activity.values:
                activity_values += [
                    {
                        "datetime": v.datetime,
                        "steps": v.steps,
                        "calories": v.calories,
                        "distanceKm": v.distanceKm,
                        "sportValue": v.sportValue,
                    }
                    for v in block.activity.values
                ]

        if block.respiratoryRate and block.respiratoryRate.values:
            rr_values += [{"datetime": v.datetime, "value": v.value} for v in block.respiratoryRate.values]

        if block.apnea:
            apnea_results += [{"datetime": v.datetime, "value": v.value} for v in (block.apnea.apneaResults or [])]
            hypoxia_times += [{"datetime": v.datetime, "value": v.value} for v in (block.apnea.hypoxiaTimes or [])]
            is_hypoxias += [{"datetime": v.datetime, "value": v.value} for v in (block.apnea.isHypoxias or [])]

        if block.cardiacLoad and block.cardiacLoad.values:
            cl_values += [{"datetime": v.datetime, "value": v.value} for v in block.cardiacLoad.values]

        if block.sportStatus:
            if block.sportStatus.version is not None:
                sport_status_version = block.sportStatus.version
            sport_status_values += [{"datetime": v.datetime, "value": v.value} for v in (block.sportStatus.values or [])]

        if block.bloodGlucose and block.bloodGlucose.value is not None:
            blood_glucose = {"value": block.bloodGlucose.value, "datetime": block.bloodGlucose.datetime}

        if block.bloodComponent:
            bc = block.bloodComponent
            blood_component = {
                "datetime": bc.datetime,
                "uricAcid": bc.uricAcid,
                "tCHO": bc.tCHO,
                "tAG": bc.tAG,
                "hDL": bc.hDL,
                "lDL": bc.lDL,
            }

    if hr_values:
        nums = [v["value"] for v in hr_values]
        record.heart_rate = {"avg": _avg(nums), "min": min(nums), "max": max(nums), "values": hr_values}

    if bp_values:
        record.blood_pressure = {
            "systolicAvg": _avg([v["systolic"] for v in bp_values]),
            "diastolicAvg": _avg([v["diastolic"] for v in bp_values]),
            "values": bp_values,
        }

    if bo_values:
        nums = [v["value"] for v in bo_values]
        record.blood_oxygen = {"avg": _avg(nums), "min": min(nums), "max": max(nums), "values": bo_values}

    if bt_values:
        record.body_temperature = {"avg": _avg([v["value"] for v in bt_values]), "values": bt_values}

    if st_values:
        record.skin_temperature = {"avg": _avg([v["value"] for v in st_values]), "values": st_values}

    if has_activity:
        record.activity = {
            "steps": total_steps,
            "calories": round(total_calories, 2),
            "distanceKm": round(total_distance, 3),
            "sportValue": total_sport_value,
            "values": activity_values,
        }

    if rr_values:
        record.respiratory_rate = {"avg": _avg([v["value"] for v in rr_values]), "values": rr_values}

    if apnea_results or hypoxia_times or is_hypoxias:
        record.apnea = {"apneaResults": apnea_results, "hypoxiaTimes": hypoxia_times, "isHypoxias": is_hypoxias}

    if cl_values:
        record.cardiac_load = {"avg": _avg([v["value"] for v in cl_values]), "values": cl_values}

    if sport_status_values or sport_status_version is not None:
        record.sport_status = {"version": sport_status_version, "values": sport_status_values}

    if blood_glucose:
        record.blood_glucose = blood_glucose

    if blood_component:
        record.blood_component = blood_component

    db.commit()


# ── Shared windowed metric extraction ───────────────────────────────────────


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


# ── POST /health/{device_id}/daily ──────────────────────────────────────────


def get_daily_status(
    db: Session, device: Device, date_str: str, start_time_str: str, end_time_str: str
) -> dict | None:
    record_date = date_cls.fromisoformat(date_str)
    compare_date = record_date - timedelta(days=1)
    start_t = time_cls.fromisoformat(start_time_str)
    end_t = time_cls.fromisoformat(end_time_str)

    record = (
        db.query(HealthRecord)
        .filter(HealthRecord.device_id == device.id, HealthRecord.date == record_date)
        .first()
    )
    if record is None:
        return None

    previous_record = (
        db.query(HealthRecord)
        .filter(HealthRecord.device_id == device.id, HealthRecord.date == compare_date)
        .first()
    )

    current = _day_metrics(record, start_t, end_t)
    previous = _day_metrics(previous_record, start_t, end_t)
    metrics, statuses = _build_metrics(current, previous)

    return {
        "device_id": device.id,
        "date": record_date.isoformat(),
        "compare_date": compare_date.isoformat(),
        "period": {"start_time": start_time_str, "end_time": end_time_str},
        "overall_status": health_rules.majority_status(statuses),
        "summary": _summary(statuses),
        "metrics": metrics,
    }


