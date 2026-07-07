import json
from datetime import date, datetime, timedelta, timezone

from sqlalchemy.orm import Session

from src.core import ai_client
from src.core.logging import logger
from src.device.models.activity_model import ActivityRecord
from src.device.models.device_model import DeviceRecord
from src.device.models.health_model import HealthRecord
from src.device.models.sleep_model import SleepRecord
from src.health.models.health_insight_model import HealthInsightRecord
from src.health.models.person_info_model import PersonInfoRecord
from src.health.schemas.health_insight_schema import BaseHealthInsightResponse, HealthInsightMetrics
from src.health.services.errors import HealthError

_LOOKBACK_DAYS = 7

_BASELINE_SYSTEM_PROMPT = """You are an AI health analysis assistant. You will receive a user's basic health
profile (sex, age, height, weight, allergy, medical history) together with their average data over the last 7
days: vital signs (heart rate, blood pressure, blood oxygen, body temperature, HRV, respiratory rate, stress),
sleep (quality score, total daily sleep duration — each day's sleep segments already summed, then averaged
across the 7 days — given as both "sleepDuration" in minutes and "sleepDurationHours" in hours, same value,
two units), and activity (step count).

Using the profile, establish a personalized baseline "normal" range for each metric below, then compare the
7-day average data against that baseline to decide a status label for each metric.

Return a JSON object with exactly these keys:
{
  "health_score": <number 0-100, overall health score>,
  "health_score_label": <string>,
  "health_score_threshold": "<low>|<mid>|<high>",
  "heart_rate": <number>,
  "heart_rate_label": <string>,
  "heart_rate_threshold": "<low>|<mid>|<high>",
  "blood_pressure": "<systolic>/<diastolic>",
  "blood_pressure_label": <string>,
  "blood_pressure_threshold": "<low_sys>/<low_dia>|<mid_sys>/<mid_dia>|<high_sys>/<high_dia>",
  "blood_oxygen": <number>,
  "blood_oxygen_label": <string>,
  "blood_oxygen_threshold": "<low>|<mid>|<high>",
  "body_temperature": <number>,
  "body_temperature_label": <string>,
  "body_temperature_threshold": "<low>|<mid>|<high>",
  "hrv": <number>,
  "hrv_label": <string>,
  "hrv_threshold": "<low>|<mid>|<high>",
  "res_rate": <number>,
  "res_rate_label": <string>,
  "res_rate_threshold": "<low>|<mid>|<high>",
  "pressure": <number>,
  "pressure_label": <string>,
  "pressure_threshold": "<low>|<mid>|<high>",
  "sleep_quality": <number>,
  "sleep_quality_label": <string>,
  "sleep_quality_threshold": "<low>|<mid>|<high>",
  "sleep_duration": <number, minutes>,
  "sleep_duration_label": <string>,
  "sleep_duration_threshold": "<low>|<mid>|<high>",
  "activity_steps": <number>,
  "activity_steps_label": <string>,
  "activity_steps_threshold": "<low>|<mid>|<high>",
  "sleep_summary": <string>,
  "activity_summary": <string>,
  "health_summary": <string>
}

Rules:
- Every "*_label" field must be exactly one of: 正常, 穩定, 注意 (do not translate these three words,
  regardless of the response language instructed below; they must always stay in Traditional Chinese).
- Each "*_threshold" field must be a personalized baseline expressed as three values separated by "|",
  derived from the user's profile, not a generic clinical constant.
- "sleep_summary" covers only sleep_quality/sleep_duration; "activity_summary" covers only activity_steps;
  "health_summary" covers only the vital-sign metrics (heart rate, blood pressure, blood oxygen, body
  temperature, HRV, respiratory rate, stress, health_score). Do not mix categories across these three summaries.
- Only the three "*_summary" fields should follow the language instruction below.
- Do not diagnose disease or recommend medication or medical treatment.
- Base the analysis only on the provided data; if data for a metric is missing, still return your best
  estimate of the label using the available profile and data, never omit a key.
- Return JSON only."""


def _average(values: list[float | None]) -> float | None:
    present = [v for v in values if v is not None]
    if not present:
        return None
    return round(sum(present) / len(present), 1)


def _week_dates(end_date: date, days: int) -> list[str]:
    return [(end_date - timedelta(days=i)).isoformat() for i in range(days - 1, -1, -1)]


def _field(row: HealthRecord, key: str, sub_key: str) -> float | None:
    data = row.data or {}
    sub = data.get(key)
    return sub.get(sub_key) if sub else None


def _aggregate_week_health(db: Session, device_id: int, dates: list[str]) -> dict:
    rows = (
        db.query(HealthRecord)
        .filter(HealthRecord.device_id == device_id, HealthRecord.date.in_(dates))
        .all()
    )
    return {
        "heartRate": _average([_field(r, "heartRate", "ppgs") for r in rows]),
        "systolic": _average([_field(r, "bloodPressure", "systolic") for r in rows]),
        "diastolic": _average([_field(r, "bloodPressure", "diastolic") for r in rows]),
        "bloodOxygen": _average([_field(r, "bloodOxygen", "oxygens") for r in rows]),
        "bodyTemperature": _average([_field(r, "bodyTemperature", "temperature") for r in rows]),
        "hrv": _average([_field(r, "hrv", "values") for r in rows]),
        "respiratoryRate": _average([_field(r, "respiratory", "resRates") for r in rows]),
        "stress": _average([_field(r, "stress", "pressure") for r in rows]),
        "daysWithData": len(rows),
    }


def _aggregate_week_sleep_activity(db: Session, device_id: int, dates: list[str]) -> dict:
    sleep_rows = (
        db.query(SleepRecord)
        .filter(SleepRecord.device_id == device_id, SleepRecord.date.in_(dates))
        .all()
    )
    activity_rows = (
        db.query(ActivityRecord)
        .filter(ActivityRecord.device_id == device_id, ActivityRecord.date.in_(dates))
        .all()
    )
    sleep_duration_minutes = _average([(row.sleep_summary or {}).get("allSleepTime") for row in sleep_rows])
    return {
        "sleepQuality": _average([(row.sleep_summary or {}).get("sleepQuality") for row in sleep_rows]),
        # kept in minutes (matches SleepRecord/illness-recovery's unit); hours included only as a
        # human-readable hint for the AI prompt, not a separate source of truth.
        "sleepDuration": sleep_duration_minutes,
        "sleepDurationHours": round(sleep_duration_minutes / 60, 2) if sleep_duration_minutes is not None else None,
        "activitySteps": _average([(row.data or {}).get("stepValue") for row in activity_rows]),
    }


def _person_info_payload(info: PersonInfoRecord) -> dict:
    return {
        "sex": info.sex,
        "age": info.age,
        "height": info.height,
        "weight": info.weight,
        "allergy": info.allergy or "無",
        "medicalHistory": info.medical_history or "無",
    }


def _generate_baseline(payload: dict, language: str) -> dict:
    prompt = ai_client.with_language(_BASELINE_SYSTEM_PROMPT, language)
    try:
        result, _usage = ai_client.generate_json(prompt, f"Input:\n{json.dumps(payload, default=str)}")
        return result
    except Exception as e:  # noqa: BLE001
        logger.exception("AI base health insight generation failed")
        raise HealthError(502, f"Unable to generate health insight: {e}") from e


_FALLBACK_LABEL = "資料不足"
_FALLBACK_THRESHOLD = "-"
_FALLBACK_SUMMARY = {"en": "Not enough data to generate a summary.", "zh": "資料不足，無法產生摘要。"}

# metric -> raw weekly-average key used to backfill a value the AI left out
_METRIC_RAW_KEYS = {
    "heart_rate": "heartRate",
    "blood_oxygen": "bloodOxygen",
    "body_temperature": "bodyTemperature",
    "hrv": "hrv",
    "res_rate": "respiratoryRate",
    "pressure": "stress",
    "sleep_quality": "sleepQuality",
    "sleep_duration": "sleepDuration",
    "activity_steps": "activitySteps",
}


def _fill_missing_metrics(result: dict, raw: dict, language: str) -> dict:
    """Defensive fallback: the prompt asks the AI to never omit a key, but if it does anyway,
    backfill the value from the raw weekly average and a neutral label/threshold instead of
    silently returning nulls to the client."""
    filled = dict(result)

    for metric, raw_key in _METRIC_RAW_KEYS.items():
        if filled.get(metric) is None:
            filled[metric] = raw.get(raw_key)
        if not filled.get(f"{metric}_label"):
            filled[f"{metric}_label"] = _FALLBACK_LABEL
        if not filled.get(f"{metric}_threshold"):
            filled[f"{metric}_threshold"] = _FALLBACK_THRESHOLD

    if not filled.get("blood_pressure"):
        systolic, diastolic = raw.get("systolic"), raw.get("diastolic")
        filled["blood_pressure"] = f"{systolic}/{diastolic}" if systolic is not None and diastolic is not None else None
    if not filled.get("blood_pressure_label"):
        filled["blood_pressure_label"] = _FALLBACK_LABEL
    if not filled.get("blood_pressure_threshold"):
        filled["blood_pressure_threshold"] = _FALLBACK_THRESHOLD

    # health_score is a synthesized score with no single raw source to backfill from;
    # only its label/threshold get a neutral fallback if the AI omitted them.
    if not filled.get("health_score_label"):
        filled["health_score_label"] = _FALLBACK_LABEL
    if not filled.get("health_score_threshold"):
        filled["health_score_threshold"] = _FALLBACK_THRESHOLD

    fallback_summary = _FALLBACK_SUMMARY.get(language, _FALLBACK_SUMMARY["en"])
    for key in ("sleep_summary", "activity_summary", "health_summary"):
        if not filled.get(key):
            filled[key] = fallback_summary

    return filled


def _next_session(db: Session, device_id: int) -> int:
    last = (
        db.query(HealthInsightRecord)
        .filter(HealthInsightRecord.device_id == device_id)
        .order_by(HealthInsightRecord.session.desc())
        .first()
    )
    return (last.session + 1) if last else 1


def _to_response(mac_address: str, record: HealthInsightRecord) -> BaseHealthInsightResponse:
    return BaseHealthInsightResponse(
        session=record.session,
        user=mac_address,
        start_date=record.start_date,
        end_date=record.end_date,
        metrics=HealthInsightMetrics(
            health_score=record.health_score,
            health_score_label=record.health_score_label,
            health_score_threshold=record.health_score_threshold,
            heart_rate=record.heart_rate,
            heart_rate_label=record.heart_rate_label,
            heart_rate_threshold=record.heart_rate_threshold,
            blood_pressure=record.blood_pressure,
            blood_pressure_label=record.blood_pressure_label,
            blood_pressure_threshold=record.blood_pressure_threshold,
            blood_oxygen=record.blood_oxygen,
            blood_oxygen_label=record.blood_oxygen_label,
            blood_oxygen_threshold=record.blood_oxygen_threshold,
            body_temperature=record.body_temperature,
            body_temperature_label=record.body_temperature_label,
            body_temperature_threshold=record.body_temperature_threshold,
            hrv=record.hrv,
            hrv_label=record.hrv_label,
            hrv_threshold=record.hrv_threshold,
            res_rate=record.res_rate,
            res_rate_label=record.res_rate_label,
            res_rate_threshold=record.res_rate_threshold,
            pressure=record.pressure,
            pressure_label=record.pressure_label,
            pressure_threshold=record.pressure_threshold,
            sleep_quality=record.sleep_quality,
            sleep_quality_label=record.sleep_quality_label,
            sleep_quality_threshold=record.sleep_quality_threshold,
            sleep_duration=record.sleep_duration,
            sleep_duration_label=record.sleep_duration_label,
            sleep_duration_threshold=record.sleep_duration_threshold,
            activity_steps=record.activity_steps,
            activity_steps_label=record.activity_steps_label,
            activity_steps_threshold=record.activity_steps_threshold,
        ),
        sleep_summary=record.sleep_summary or "",
        activity_summary=record.activity_summary or "",
        health_summary=record.health_summary or "",
    )


def generate_base_health_insight(
    db: Session, mac_address: str, language: str = "en"
) -> BaseHealthInsightResponse:
    device = db.query(DeviceRecord).filter(DeviceRecord.mac_address == mac_address).first()
    if device is None:
        raise HealthError(404, "找不到對應設備")

    person_info = db.query(PersonInfoRecord).filter(PersonInfoRecord.device_id == device.id).first()
    if person_info is None:
        raise HealthError(400, "請先上傳個人健康基礎信息")

    end_date = datetime.now(timezone.utc).date()
    start_date = end_date - timedelta(days=_LOOKBACK_DAYS - 1)
    dates = _week_dates(end_date, _LOOKBACK_DAYS)

    week_agg = _aggregate_week_health(db, device.id, dates)
    if week_agg["daysWithData"] == 0:
        raise HealthError(404, "近7天無健康數據，無法產生分析")

    sleep_activity_agg = _aggregate_week_sleep_activity(db, device.id, dates)

    payload = {
        "personInfo": _person_info_payload(person_info),
        "startDate": start_date.isoformat(),
        "endDate": end_date.isoformat(),
        "weeklyAverageData": {**week_agg, **sleep_activity_agg},
    }
    result = _generate_baseline(payload, language)
    result = _fill_missing_metrics(result, {**week_agg, **sleep_activity_agg}, language)

    session = _next_session(db, device.id)
    record = HealthInsightRecord(
        device_id=device.id,
        session=session,
        start_date=start_date.isoformat(),
        end_date=end_date.isoformat(),
        health_score=result.get("health_score"),
        health_score_label=result.get("health_score_label"),
        health_score_threshold=result.get("health_score_threshold"),
        heart_rate=result.get("heart_rate"),
        heart_rate_label=result.get("heart_rate_label"),
        heart_rate_threshold=result.get("heart_rate_threshold"),
        blood_pressure=result.get("blood_pressure"),
        blood_pressure_label=result.get("blood_pressure_label"),
        blood_pressure_threshold=result.get("blood_pressure_threshold"),
        blood_oxygen=result.get("blood_oxygen"),
        blood_oxygen_label=result.get("blood_oxygen_label"),
        blood_oxygen_threshold=result.get("blood_oxygen_threshold"),
        body_temperature=result.get("body_temperature"),
        body_temperature_label=result.get("body_temperature_label"),
        body_temperature_threshold=result.get("body_temperature_threshold"),
        hrv=result.get("hrv"),
        hrv_label=result.get("hrv_label"),
        hrv_threshold=result.get("hrv_threshold"),
        res_rate=result.get("res_rate"),
        res_rate_label=result.get("res_rate_label"),
        res_rate_threshold=result.get("res_rate_threshold"),
        pressure=result.get("pressure"),
        pressure_label=result.get("pressure_label"),
        pressure_threshold=result.get("pressure_threshold"),
        sleep_quality=result.get("sleep_quality"),
        sleep_quality_label=result.get("sleep_quality_label"),
        sleep_quality_threshold=result.get("sleep_quality_threshold"),
        sleep_duration=result.get("sleep_duration"),
        sleep_duration_label=result.get("sleep_duration_label"),
        sleep_duration_threshold=result.get("sleep_duration_threshold"),
        activity_steps=result.get("activity_steps"),
        activity_steps_label=result.get("activity_steps_label"),
        activity_steps_threshold=result.get("activity_steps_threshold"),
        sleep_summary=result.get("sleep_summary", ""),
        activity_summary=result.get("activity_summary", ""),
        health_summary=result.get("health_summary", ""),
    )
    db.add(record)
    db.commit()
    db.refresh(record)

    return _to_response(mac_address, record)
