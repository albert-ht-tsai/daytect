from datetime import date as date_cls
from datetime import datetime, timezone

from sqlalchemy.orm import Session

from src.health.models.health_record_model import HealthRecord
from src.health.schemas.health_schema import UploadDailyHealthRequest
from src.health.services import health_metrics
from src.user_device.models.device_model import Device


def _avg(values: list) -> float | None:
    clean = [v for v in values if v is not None]
    return round(sum(clean) / len(clean), 2) if clean else None


def upload_daily_health(db: Session, device: Device, body: UploadDailyHealthRequest) -> None:
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

    if body.sleep:
        s = body.sleep
        record.sleep = {
            "date": s.date,
            "sleep_quality": s.sleepQuality,
            "wake_count": s.wakeCount,
            "deep_sleep_minutes": s.deepSleepMinutes,
            "light_sleep_minutes": s.lightSleepMinutes,
            "total": s.totalSleepMinutes,
            "sleep_down_time": s.sleepDownTime,
            "sleep_up_time": s.sleepUpTime,
            "sleep_line": s.sleepLine,
            "sleep_line_records": [
                {"datetime": r.datetime, "state": r.state, "rawValue": r.rawValue}
                for r in (s.sleepLineRecords or [])
            ],
        }

    hr_values: list[dict] = []
    bp_values: list[dict] = []
    bo_values: list[dict] = []
    bt_values: list[dict] = []
    st_values: list[dict] = []
    rr_values: list[dict] = []
    ss_values: list[dict] = []
    apnea_results: list[dict] = []
    hypoxia_times: list[dict] = []
    is_hypoxias: list[dict] = []
    cl_values: list[dict] = []
    sport_status_values: list[dict] = []
    sport_status_version: int | None = None
    has_activity = False
    total_steps = 0
    total_calories = 0.0
    total_distance = 0.0
    blood_glucose_vals: list[float] = []
    bc_uric_acid: list[float] = []
    bc_tcho: list[float] = []
    bc_tag: list[float] = []
    bc_hdl: list[float] = []
    bc_ldl: list[float] = []

    for block in body.healthRecords:
        if block.heartRate and block.heartRate.values:
            for v in block.heartRate.values:
                hr_values.append({"datetime": v.datetime, "value": v.value, "unit": "bpm"})

        if block.bloodPressure and block.bloodPressure.values:
            for v in block.bloodPressure.values:
                bp_values.append({"datetime": v.datetime, "systolic": v.systolic, "diastolic": v.diastolic})

        if block.bloodOxygen and block.bloodOxygen.values:
            for v in block.bloodOxygen.values:
                bo_values.append({"datetime": v.datetime, "value": v.value, "unit": "%"})

        if block.bodyTemperature and block.bodyTemperature.values:
            for v in block.bodyTemperature.values:
                bt_values.append({"datetime": v.datetime, "value": v.value, "unit": "°C"})

        if block.skinTemperature and block.skinTemperature.values:
            for v in block.skinTemperature.values:
                st_values.append({"datetime": v.datetime, "value": v.value, "unit": "°C"})

        if block.activity:
            has_activity = True
            total_steps += block.activity.steps or 0
            total_calories += block.activity.calories or 0.0
            total_distance += block.activity.distanceKm or 0.0

        if block.respiratoryRate and block.respiratoryRate.values:
            for v in block.respiratoryRate.values:
                rr_values.append({"datetime": v.datetime, "value": v.value})

        if block.sleepState and block.sleepState.values:
            for v in block.sleepState.values:
                ss_values.append({"datetime": v.datetime, "value": v.value})

        if block.apnea:
            for v in block.apnea.apneaResults or []:
                apnea_results.append({"datetime": v.datetime, "value": v.value})
            for v in block.apnea.hypoxiaTimes or []:
                hypoxia_times.append({"datetime": v.datetime, "value": v.value})
            for v in block.apnea.isHypoxias or []:
                is_hypoxias.append({"datetime": v.datetime, "value": v.value})

        if block.cardiacLoad and block.cardiacLoad.values:
            for v in block.cardiacLoad.values:
                cl_values.append({"datetime": v.datetime, "value": v.value})

        if block.sportStatus:
            if block.sportStatus.version is not None:
                sport_status_version = block.sportStatus.version
            for v in block.sportStatus.values or []:
                sport_status_values.append({"datetime": v.datetime, "value": v.value})

        if block.bloodGlucose and block.bloodGlucose.value is not None:
            blood_glucose_vals.append(block.bloodGlucose.value)

        if block.bloodComponent:
            bc = block.bloodComponent
            if bc.uricAcid is not None:
                bc_uric_acid.append(bc.uricAcid)
            if bc.tCHO is not None:
                bc_tcho.append(bc.tCHO)
            if bc.tAG is not None:
                bc_tag.append(bc.tAG)
            if bc.hDL is not None:
                bc_hdl.append(bc.hDL)
            if bc.lDL is not None:
                bc_ldl.append(bc.lDL)

    if hr_values:
        record.heart_rate = hr_values

    if bp_values:
        systolics = [v["systolic"] for v in bp_values]
        diastolics = [v["diastolic"] for v in bp_values]
        record.blood_pressure = {
            "systolic": _avg(systolics),
            "diastolic": _avg(diastolics),
            "unit": "mmHg",
            "values": bp_values,
        }

    if bo_values:
        record.blood_oxygen = {
            "value": _avg([v["value"] for v in bo_values]),
            "unit": "%",
            "values": bo_values,
        }

    if bt_values:
        record.body_temperature = {
            "value": _avg([v["value"] for v in bt_values]),
            "unit": "°C",
            "values": bt_values,
        }

    if st_values:
        record.skin_temperature = {
            "value": _avg([v["value"] for v in st_values]),
            "unit": "°C",
            "values": st_values,
        }

    if has_activity:
        record.activity = {
            "steps": total_steps,
            "calories": round(total_calories, 2),
            "distance_km": round(total_distance, 3),
        }

    if rr_values:
        record.respiratory_rate = {
            "value": _avg([v["value"] for v in rr_values]),
            "values": rr_values,
        }

    if ss_values:
        record.sleep_state = {"values": ss_values}

    if apnea_results or hypoxia_times or is_hypoxias:
        record.apnea = {
            "apnea_results": apnea_results,
            "hypoxia_times": hypoxia_times,
            "is_hypoxias": is_hypoxias,
        }

    if cl_values:
        record.cardiac_load = {
            "value": _avg([v["value"] for v in cl_values]),
            "values": cl_values,
        }

    if sport_status_values:
        record.sport_status = {"version": sport_status_version, "values": sport_status_values}

    bc: dict[str, float] = {}
    if blood_glucose_vals:
        bc["blood_glucose"] = _avg(blood_glucose_vals)
    if bc_uric_acid:
        bc["uric_acid"] = _avg(bc_uric_acid)
    if bc_tcho:
        bc["total_cholesterol"] = _avg(bc_tcho)
    if bc_tag:
        bc["triglyceride"] = _avg(bc_tag)
    if bc_hdl:
        bc["hdl"] = _avg(bc_hdl)
    if bc_ldl:
        bc["ldl"] = _avg(bc_ldl)
    if bc:
        record.blood_components = bc

    db.commit()


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
