import json
from datetime import datetime, timedelta

from sqlalchemy.orm import Session

from src.analysis.models.illness_recovery_model import IllnessRecoveryRecord
from src.analysis.schemas.illness_recovery_schema import IllnessRecoveryResponse
from src.analysis.services import illness_recovery_rules as rules
from src.analysis.services.errors import AnalysisError
from src.core import ai_client
from src.core.logging import logger
from src.device.models.activity_model import ActivityRecord
from src.device.models.device_model import DeviceRecord
from src.device.models.health_model import HealthRecord
from src.device.models.sleep_model import SleepRecord
from src.health.models.person_info_model import PersonInfoRecord

BASELINE_WINDOW_DAYS = 30
RECENT_DAYS = 3  # trailing days evaluated for persistence/trend (rule 4/8)
HIGH_ACTIVITY_RATIO = 1.3
LOW_SLEEP_RATIO = 0.85

_SUMMARY_SYSTEM_PROMPT = """You are a health data analysis assistant describing a user's illness/recovery
status. You will receive the user's basic profile together with ALREADY-DECIDED classification labels
(illness_level, recovery_status, trend, joint_status), an ALREADY-COMPUTED list of main findings, and an
optional alternative explanation. Write a short, natural-language narrative summary describing today's status
for the user, referencing the given findings.
Return a JSON object: {"summary": "<string>"}
Rules:
- Do NOT invent new numbers or findings beyond what is given.
- Do NOT change, contradict, or re-derive the given labels; treat them as fixed conclusions to explain.
- Do not diagnose a specific disease and do not claim the user is definitely sick or definitely healthy.
- If mainFindings is empty, say no clear multi-metric deviation was found.
- Use clear, simple, empathetic language.
- Return JSON only."""


def _field(row: HealthRecord, key: str, sub_key: str) -> float | None:
    data = row.data or {}
    sub = data.get(key)
    value = sub.get(sub_key) if sub else None
    return float(value) if value is not None else None


def _date_range(end_date_str: str, days: int) -> list[str]:
    end_date = datetime.strptime(end_date_str, "%Y-%m-%d").date()
    return [(end_date - timedelta(days=i)).isoformat() for i in range(days - 1, -1, -1)]


def _daily_metrics_map(db: Session, device_id: int, dates: list[str]) -> dict[str, dict]:
    by_date: dict[str, dict] = {d: {} for d in dates}

    health_rows = db.query(HealthRecord).filter(
        HealthRecord.device_id == device_id, HealthRecord.date.in_(dates)
    ).all()
    for row in health_rows:
        by_date[row.date]["resting_hr"] = _field(row, "heartRate", "ppgs")
        by_date[row.date]["body_temperature"] = _field(row, "bodyTemperature", "temperature")
        by_date[row.date]["hrv"] = _field(row, "hrv", "values")

    sleep_rows = db.query(SleepRecord).filter(
        SleepRecord.device_id == device_id, SleepRecord.date.in_(dates)
    ).all()
    for row in sleep_rows:
        summary = row.sleep_summary or {}
        by_date[row.date]["sleep_quality"] = summary.get("sleepQuality")
        by_date[row.date]["sleep_duration"] = summary.get("allSleepTime")

    activity_rows = db.query(ActivityRecord).filter(
        ActivityRecord.device_id == device_id, ActivityRecord.date.in_(dates)
    ).all()
    for row in activity_rows:
        by_date[row.date]["activity_steps"] = (row.data or {}).get("stepValue")

    return by_date


def _compute_baseline(by_date: dict[str, dict], baseline_dates: list[str]) -> dict[str, float | None]:
    baseline: dict[str, float | None] = {}
    for metric in rules.METRIC_RULES:
        values = [by_date[d].get(metric) for d in baseline_dates if by_date[d].get(metric) is not None]
        baseline[metric] = round(sum(values) / len(values), 2) if values else None
    return baseline


def _person_info_payload(info: PersonInfoRecord | None) -> dict:
    if info is None:
        return {}
    return {
        "sex": info.sex,
        "age": info.age,
        "height": info.height,
        "weight": info.weight,
        "allergy": info.allergy or "無",
        "medicalHistory": info.medical_history or "無",
    }


def _generate_summary_text(payload: dict, language: str) -> str:
    prompt = ai_client.with_language(_SUMMARY_SYSTEM_PROMPT, language)
    try:
        result, _usage = ai_client.generate_json(prompt, f"Input:\n{json.dumps(payload, default=str)}")
        return result.get("summary", "")
    except Exception as e:  # noqa: BLE001
        logger.exception("AI illness/recovery summary generation failed")
        return f"Unable to generate summary: {e}"


def _to_response(mac_address: str, record: IllnessRecoveryRecord) -> IllnessRecoveryResponse:
    return IllnessRecoveryResponse(
        id=record.id,
        macAddress=mac_address,
        date=record.date,
        illness_level=record.illness_level,
        recovery_status=record.recovery_status,
        trend=record.trend,
        joint_status=record.joint_status,
        main_findings=record.main_findings or [],
        alternative_explanation=record.alternative_explanation,
        summary=record.summary or "",
    )


def generate_illness_recovery(
    db: Session, mac_address: str, date: str, language: str = "en"
) -> IllnessRecoveryResponse:
    device = db.query(DeviceRecord).filter(DeviceRecord.mac_address == mac_address).first()
    if device is None:
        raise AnalysisError(404, "找不到對應設備")

    all_dates = _date_range(date, BASELINE_WINDOW_DAYS)
    baseline_dates, recent_dates = all_dates[:-RECENT_DAYS], all_dates[-RECENT_DAYS:]
    by_date = _daily_metrics_map(db, device.id, all_dates)

    baseline_days_with_data = sum(1 for d in baseline_dates if any(v is not None for v in by_date[d].values()))
    today_has_data = any(v is not None for v in by_date[date].values())
    if baseline_days_with_data == 0 and not today_has_data:
        raise AnalysisError(404, "近期無健康數據，無法產生分析")

    baseline = _compute_baseline(by_date, baseline_dates)
    data_sufficient = baseline_days_with_data >= rules.MIN_BASELINE_DAYS and today_has_data

    day_signals = [rules.evaluate_day(d, by_date[d], baseline) for d in recent_dates]

    yesterday = by_date[recent_dates[-2]] if len(recent_dates) >= 2 else {}
    activity_baseline, yesterday_activity = baseline.get("activity_steps"), yesterday.get("activity_steps")
    high_activity_recent = bool(
        activity_baseline and yesterday_activity and yesterday_activity >= activity_baseline * HIGH_ACTIVITY_RATIO
    )
    sleep_baseline, yesterday_sleep = baseline.get("sleep_duration"), yesterday.get("sleep_duration")
    sleep_insufficient_recent = bool(
        sleep_baseline and yesterday_sleep and yesterday_sleep <= sleep_baseline * LOW_SLEEP_RATIO
    )

    illness_level = rules.classify_illness_level(
        day_signals, high_activity_recent, sleep_insufficient_recent, data_sufficient
    )
    recovery_status = rules.classify_recovery_status(day_signals, data_sufficient)
    trend = rules.classify_trend(day_signals, data_sufficient)
    joint_status = rules.classify_joint_status(illness_level, recovery_status)
    main_findings = rules.build_evidence(day_signals[-1], language) if data_sufficient else []
    alternative_explanation = rules.build_alternative_explanation(
        high_activity_recent, sleep_insufficient_recent, language
    )

    person_info = db.query(PersonInfoRecord).filter(PersonInfoRecord.device_id == device.id).first()
    payload = {
        "personInfo": _person_info_payload(person_info),
        "date": date,
        "illness_level": illness_level,
        "recovery_status": recovery_status,
        "trend": trend,
        "joint_status": joint_status,
        "mainFindings": main_findings,
        "alternativeExplanation": alternative_explanation,
    }
    summary_text = _generate_summary_text(payload, language)

    existing = db.query(IllnessRecoveryRecord).filter(
        IllnessRecoveryRecord.device_id == device.id, IllnessRecoveryRecord.date == date
    ).first()
    if existing is None:
        existing = IllnessRecoveryRecord(device_id=device.id, date=date)
        db.add(existing)

    existing.illness_level = illness_level
    existing.recovery_status = recovery_status
    existing.trend = trend
    existing.joint_status = joint_status
    existing.main_findings = main_findings
    existing.alternative_explanation = alternative_explanation
    existing.summary = summary_text
    db.commit()
    db.refresh(existing)

    return _to_response(mac_address, existing)


def get_illness_recovery(db: Session, mac_address: str, date: str) -> IllnessRecoveryResponse | None:
    device = db.query(DeviceRecord).filter(DeviceRecord.mac_address == mac_address).first()
    if device is None:
        return None
    record = db.query(IllnessRecoveryRecord).filter(
        IllnessRecoveryRecord.device_id == device.id, IllnessRecoveryRecord.date == date
    ).first()
    if record is None:
        return None
    return _to_response(mac_address, record)
