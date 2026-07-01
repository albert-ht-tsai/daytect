import json

from sqlalchemy.orm import Session

from src.core import ai_client
from src.core.logging import logger
from src.device.models.activity_model import ActivityRecord
from src.device.models.device_model import DeviceRecord
from src.device.models.health_model import HealthRecord
from src.device.models.sleep_model import SleepRecord
from src.summary.models.summary_model import DailyHealthSummaryRecord
from src.summary.schemas.summary_schema import (
    CategoryResult,
    DailyHealthSummaryResponse,
    OverallResult,
    SummaryRecords,
)
from src.summary.services import scoring

_CATEGORY_WEIGHT = 1 / 3

_SLEEP_SYSTEM_PROMPT = """You are a health data analysis assistant.
Analyze one day of wearable sleep data and return a JSON object:
{"summary": "<string>", "suggestion": "<string>"}
Rules:
- Do not diagnose disease or recommend medication or medical treatment.
- Base the summary only on the provided data; if data is insufficient, state so clearly.
- Use clear, simple language.
- Return JSON only."""

_ACTIVITY_SYSTEM_PROMPT = """You are a health data analysis assistant.
Analyze one day of wearable activity data (steps, calories, distance) and return a JSON object:
{"summary": "<string>", "suggestion": "<string>"}
Rules:
- Do not diagnose disease or recommend medication or medical treatment.
- Base the summary only on the provided data; if data is insufficient, state so clearly.
- Use clear, simple language.
- Return JSON only."""

_HEALTH_SYSTEM_PROMPT = """You are a health data analysis assistant.
Analyze one day of wearable vital-sign data (heart rate, blood pressure, blood oxygen,
body temperature, respiratory rate, stress) and return a JSON object:
{"summary": "<string>", "suggestion": "<string>"}
Rules:
- Do not diagnose disease or recommend medication or medical treatment.
- Do not overstate risks.
- Base the summary only on the provided data; if data is insufficient, state so clearly.
- Use clear, simple language.
- Return JSON only."""

_OVERALL_SYSTEM_PROMPT = """You are a health data analysis assistant.
You will receive a day's Sleep, Activity, and Health category scores and summaries.
Return a JSON object: {"summary": "<string>", "suggestion": "<string>"}
Rules:
- Synthesize one overall daily health picture across all three categories.
- Do not diagnose disease or recommend medication or medical treatment.
- Use clear, simple language.
- Return JSON only."""


def _aggregate_sleep(record: SleepRecord | None) -> dict:
    if record is None:
        return {}
    return {
        "sleepQuality": record.sleep_quality,
        "wakeCount": record.wake_count,
        "deepSleepTime": record.deep_sleep_time,
        "lowSleepTime": record.low_sleep_time,
        "allSleepTime": record.all_sleep_time,
    }


def _avg(values: list[float]) -> float | None:
    return round(sum(values) / len(values), 2) if values else None


def _aggregate_activity(rows: list[ActivityRecord]) -> dict:
    if not rows:
        return {}
    steps = [r.data.get("stepValue") for r in rows if r.data.get("stepValue") is not None]
    cals = [r.data.get("calValue") for r in rows if r.data.get("calValue") is not None]
    dists = [r.data.get("disValue") for r in rows if r.data.get("disValue") is not None]
    return {
        "entryCount": len(rows),
        "totalSteps": sum(steps) if steps else None,
        "totalCalories": round(sum(cals), 2) if cals else None,
        "totalDistanceKm": round(sum(dists), 2) if dists else None,
    }


def _aggregate_health(rows: list[HealthRecord]) -> dict:
    if not rows:
        return {}

    def _field(key: str, sub_key: str) -> list[float]:
        values = []
        for r in rows:
            sub = r.data.get(key)
            if sub and sub.get(sub_key) is not None:
                values.append(sub[sub_key])
        return values

    stress = _field("stress", "pressure")

    return {
        "entryCount": len(rows),
        "avgHeartRate": _avg(_field("heartRate", "ppgs")),
        "avgSystolic": _avg(_field("bloodPressure", "systolic")),
        "avgDiastolic": _avg(_field("bloodPressure", "diastolic")),
        "avgBloodOxygen": _avg(_field("bloodOxygen", "oxygens")),
        "avgBodyTemperature": _avg(_field("bodyTemperature", "temperature")),
        "avgRespiratoryRate": _avg(_field("respiratory", "resRates")),
        "avgStress": _avg(stress),
    }


def _score_sleep(agg: dict) -> float | None:
    all_sleep = agg.get("allSleepTime")
    deep_sleep = agg.get("deepSleepTime")
    deep_ratio_pct = None
    if all_sleep and deep_sleep is not None and all_sleep > 0:
        deep_ratio_pct = deep_sleep / all_sleep * 100

    quality = agg.get("sleepQuality")
    components = [
        (float(quality) if quality is not None else None, 0.4),
        (scoring.range_score(all_sleep, 420, 540, 180), 0.3),
        (scoring.range_score(deep_ratio_pct, 15, 25, 15), 0.2),
        (scoring.lower_is_better_score(agg.get("wakeCount"), 2, 6), 0.1),
    ]
    return scoring.weighted_average(components)


def _score_activity(agg: dict) -> float | None:
    components = [
        (scoring.higher_is_better_score(agg.get("totalSteps"), 8000), 0.5),
        (scoring.higher_is_better_score(agg.get("totalCalories"), 300), 0.3),
        (scoring.higher_is_better_score(agg.get("totalDistanceKm"), 5), 0.2),
    ]
    return scoring.weighted_average(components)


def _score_health(agg: dict) -> float | None:
    blood_pressure_score = scoring.weighted_average(
        [
            (scoring.range_score(agg.get("avgSystolic"), 90, 120, 30), 0.5),
            (scoring.range_score(agg.get("avgDiastolic"), 60, 80, 20), 0.5),
        ]
    )
    components = [
        (scoring.range_score(agg.get("avgHeartRate"), 60, 100, 40), 0.25),
        (blood_pressure_score, 0.2),
        (scoring.range_score(agg.get("avgBloodOxygen"), 95, 100, 10), 0.2),
        (scoring.range_score(agg.get("avgBodyTemperature"), 36.1, 37.2, 1.5), 0.1),
        (scoring.range_score(agg.get("avgRespiratoryRate"), 12, 20, 8), 0.1),
        (scoring.lower_is_better_score(agg.get("avgStress"), 40, 80), 0.15),
    ]
    return scoring.weighted_average(components)


def _generate_category_text(system_prompt: str, payload: dict) -> tuple[str, str]:
    try:
        result, _usage = ai_client.generate_json(system_prompt, f"Input:\n{json.dumps(payload, default=str)}")
        return result.get("summary", ""), result.get("suggestion", "")
    except Exception as e:  # noqa: BLE001
        logger.exception("AI summary generation failed")
        return f"Unable to generate summary: {e}", ""


def _to_response(device: DeviceRecord, record: DailyHealthSummaryRecord) -> DailyHealthSummaryResponse:
    return DailyHealthSummaryResponse(
        id=str(record.id),
        name=device.name,
        macAddress=device.mac_address,
        date=record.date,
        records=SummaryRecords(
            sleep=CategoryResult(
                score=record.sleep_score, summary=record.sleep_summary, suggestion=record.sleep_suggestion
            ),
            activity=CategoryResult(
                score=record.activity_score,
                summary=record.activity_summary,
                suggestion=record.activity_suggestion,
            ),
            health=CategoryResult(
                score=record.health_score, summary=record.health_summary, suggestion=record.health_suggestion
            ),
        ),
        overall=OverallResult(
            score=record.overall_score, summary=record.overall_summary, suggestion=record.overall_suggestion
        ),
    )


def generate_summary(db: Session, mac_address: str, date: str) -> DailyHealthSummaryResponse | None:
    device = db.query(DeviceRecord).filter(DeviceRecord.mac_address == mac_address).first()
    if device is None:
        return None

    sleep_row = db.query(SleepRecord).filter(
        SleepRecord.device_id == device.id,
        SleepRecord.date == date,
    ).first()
    activity_rows = db.query(ActivityRecord).filter(
        ActivityRecord.device_id == device.id,
        ActivityRecord.entry_datetime.like(f"{date}%"),
    ).all()
    health_rows = db.query(HealthRecord).filter(
        HealthRecord.device_id == device.id,
        HealthRecord.entry_datetime.like(f"{date}%"),
    ).all()

    sleep_agg = _aggregate_sleep(sleep_row)
    activity_agg = _aggregate_activity(activity_rows)
    health_agg = _aggregate_health(health_rows)

    sleep_score = _score_sleep(sleep_agg)
    activity_score = _score_activity(activity_agg)
    health_score = _score_health(health_agg)

    existing = db.query(DailyHealthSummaryRecord).filter(
        DailyHealthSummaryRecord.device_id == device.id,
        DailyHealthSummaryRecord.date == date,
    ).first()
    if existing is None:
        existing = DailyHealthSummaryRecord(device_id=device.id, date=date)
        db.add(existing)

    existing.sleep_score = sleep_score
    existing.sleep_summary, existing.sleep_suggestion = _generate_category_text(
        _SLEEP_SYSTEM_PROMPT, {"date": date, "score": sleep_score, "data": sleep_agg}
    )
    db.commit()

    existing.activity_score = activity_score
    existing.activity_summary, existing.activity_suggestion = _generate_category_text(
        _ACTIVITY_SYSTEM_PROMPT, {"date": date, "score": activity_score, "data": activity_agg}
    )
    db.commit()

    existing.health_score = health_score
    existing.health_summary, existing.health_suggestion = _generate_category_text(
        _HEALTH_SYSTEM_PROMPT, {"date": date, "score": health_score, "data": health_agg}
    )
    db.commit()

    existing.overall_score = scoring.weighted_average(
        [
            (sleep_score, _CATEGORY_WEIGHT),
            (activity_score, _CATEGORY_WEIGHT),
            (health_score, _CATEGORY_WEIGHT),
        ]
    )
    existing.overall_summary, existing.overall_suggestion = _generate_category_text(
        _OVERALL_SYSTEM_PROMPT,
        {
            "date": date,
            "sleep": {"score": sleep_score, "summary": existing.sleep_summary},
            "activity": {"score": activity_score, "summary": existing.activity_summary},
            "health": {"score": health_score, "summary": existing.health_summary},
        },
    )
    db.commit()
    db.refresh(existing)

    return _to_response(device, existing)


def get_summary(db: Session, mac_address: str, date: str) -> DailyHealthSummaryResponse | None:
    device = db.query(DeviceRecord).filter(DeviceRecord.mac_address == mac_address).first()
    if device is None:
        return None
    record = db.query(DailyHealthSummaryRecord).filter(
        DailyHealthSummaryRecord.device_id == device.id,
        DailyHealthSummaryRecord.date == date,
    ).first()
    if record is None:
        return None
    return _to_response(device, record)
