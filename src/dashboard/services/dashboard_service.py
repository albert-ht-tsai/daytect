from datetime import date as date_cls
from datetime import datetime, timedelta, timezone

from sqlalchemy.orm import Session

from src.core.ai_client import generate_daily, generate_periodic
from src.core.logging import logger
from src.dashboard.schemas.dashboard_schema import (
    ActivityMetric,
    BloodOxygenMetric,
    BloodPressureMetric,
    BodyTemperatureMetric,
    DashboardData,
    DashboardResponse,
    HealthHighlight,
    HealthInsight,
    HealthMetrics,
    HealthScore,
    HealthTrend,
    HeartRateMetric,
    SleepMetric,
    TodayHealthOverview,
    WeeklyActivityMetric,
    WeeklyBloodOxygenMetric,
    WeeklyBloodPressureMetric,
    WeeklyBodyTemperatureMetric,
    WeeklyHealthMetrics,
    WeeklyHealthOverview,
    WeeklyHeartRateMetric,
    WeeklySleepMetric,
)
from src.health.models.health_record_model import HealthRecord
from src.health.services import health_metrics
from src.health.services.health_service import average_heart_rate, compute_metric_statuses
from src.user_device.models.device_model import Device

_INSUFFICIENT_MESSAGES = {
    "today": (
        "More device health data is required before AI analysis can be generated. "
        "Please continue collecting health data to enable day-to-day comparison."
    ),
    "weekly": (
        "More device health data is required before AI analysis can be generated. "
        "Please continue collecting health data to enable weekly comparison."
    ),
}

_LEVEL_MAP = {
    "excellent": "excellent",
    "good": "good",
    "normal": "fair",
    "monitor": "poor",
    "warning": "poor",
    "critical": "critical",
}

_STATUS_MAP = {
    "good": "good",
    "normal": "normal",
    "low": "low",
    "high": "high",
    "monitor": "abnormal",
    "critical": "abnormal",
}

_STATUS_SEVERITY = {"good": 0, "normal": 0, "low": 1, "high": 1, "monitor": 1, "critical": 2}
_MIN_WEEKLY_DAYS = 2
_DATA_FIELDS = ("heart_rate", "blood_pressure", "blood_oxygen", "sleep", "body_temperature", "activity")


def _today() -> date_cls:
    return datetime.now(timezone.utc).date()


def _has_data(record: HealthRecord | None) -> bool:
    if record is None:
        return False
    return any(getattr(record, field) is not None for field in _DATA_FIELDS)


def _map_status(status: str | None) -> str:
    if status is None:
        return "unknown"
    return _STATUS_MAP.get(status, "abnormal")


def _map_level(level: str) -> str:
    return _LEVEL_MAP.get(level, "unknown")


def _status_trend(current_status: str | None, baseline_status: str | None) -> str:
    if current_status is None or baseline_status is None:
        return "insufficient_data"
    current_sev = _STATUS_SEVERITY.get(current_status, 1)
    baseline_sev = _STATUS_SEVERITY.get(baseline_status, 1)
    if current_sev < baseline_sev:
        return "improved"
    if current_sev > baseline_sev:
        return "declined"
    return "stable"


def _value_trend(current_value: float | None, baseline_value: float | None) -> str:
    if current_value is None or baseline_value is None:
        return "insufficient_data"
    if baseline_value == 0:
        return "stable" if current_value == 0 else "improved"
    diff_ratio = (current_value - baseline_value) / baseline_value
    if diff_ratio > 0.02:
        return "improved"
    if diff_ratio < -0.02:
        return "declined"
    return "stable"


def _score_trend(diff: int) -> str:
    if diff > 0:
        return "improved"
    if diff < 0:
        return "declined"
    return "stable"


def _avg(values: list[float | None]) -> float | None:
    clean = [v for v in values if v is not None]
    return sum(clean) / len(clean) if clean else None


def _half_split(records: list[HealthRecord]) -> tuple[list[HealthRecord], list[HealthRecord]]:
    mid = max(1, len(records) // 2)
    first = records[:mid]
    second = records[mid:] or records[:mid]
    return first, second


def _sleep_quality_score(sleep: dict | None) -> int | None:
    if not sleep:
        return None
    total = sleep.get("total")
    if not total:
        return None
    base = {"good": 85, "normal": 70, "monitor": 55, "low": 40}.get(health_metrics.sleep_status(total), 40)
    deep_ratio = (sleep.get("deep") or 0) / total
    return max(0, min(100, round(base + (deep_ratio - 0.2) * 50)))


def _record_score(record: HealthRecord) -> int:
    score, _ = health_metrics.compute_health_score(compute_metric_statuses(record))
    return score


# ---- today metrics ----


def _today_heart_rate(record: HealthRecord | None, prev_record: HealthRecord | None) -> HeartRateMetric:
    readings = sorted((record.heart_rate or []), key=lambda r: r["time"]) if record else []
    values = [r["value"] for r in readings]
    avg = average_heart_rate(record) if record else None
    status = health_metrics.heart_rate_status(avg)
    prev_status = health_metrics.heart_rate_status(average_heart_rate(prev_record) if prev_record else None)
    return HeartRateMetric(
        current=values[-1] if values else None,
        avg=avg,
        min=min(values) if values else None,
        max=max(values) if values else None,
        status=_map_status(status),
        trend=_status_trend(status, prev_status),
    )


def _today_blood_pressure(record: HealthRecord | None, prev_record: HealthRecord | None) -> BloodPressureMetric:
    bp = (record.blood_pressure or {}) if record else {}
    prev_bp = (prev_record.blood_pressure or {}) if prev_record else {}
    status = health_metrics.blood_pressure_status(bp.get("systolic"), bp.get("diastolic"))
    prev_status = health_metrics.blood_pressure_status(prev_bp.get("systolic"), prev_bp.get("diastolic"))
    return BloodPressureMetric(
        systolic=bp.get("systolic"),
        diastolic=bp.get("diastolic"),
        status=_map_status(status),
        trend=_status_trend(status, prev_status),
    )


def _today_blood_oxygen(record: HealthRecord | None, prev_record: HealthRecord | None) -> BloodOxygenMetric:
    spo2 = (record.blood_oxygen or {}).get("value") if record else None
    prev_spo2 = (prev_record.blood_oxygen or {}).get("value") if prev_record else None
    status = health_metrics.blood_oxygen_status(spo2)
    prev_status = health_metrics.blood_oxygen_status(prev_spo2)
    return BloodOxygenMetric(
        avg=spo2,
        min=spo2,
        status=_map_status(status),
        trend=_status_trend(status, prev_status),
    )


def _today_sleep(record: HealthRecord | None, prev_record: HealthRecord | None) -> SleepMetric:
    sleep = (record.sleep or {}) if record else {}
    prev_sleep = (prev_record.sleep or {}) if prev_record else {}
    total = sleep.get("total")
    prev_total = prev_sleep.get("total")
    status = health_metrics.sleep_status(total)
    return SleepMetric(
        duration=round(total / 60, 1) if total is not None else None,
        quality_score=_sleep_quality_score(sleep),
        status=_map_status(status),
        trend=_value_trend(total, prev_total),
    )


def _today_body_temperature(record: HealthRecord | None, prev_record: HealthRecord | None) -> BodyTemperatureMetric:
    temp = (record.body_temperature or {}).get("value") if record else None
    prev_temp = (prev_record.body_temperature or {}).get("value") if prev_record else None
    status = health_metrics.body_temperature_status(temp)
    prev_status = health_metrics.body_temperature_status(prev_temp)
    return BodyTemperatureMetric(
        avg=temp,
        status=_map_status(status),
        trend=_status_trend(status, prev_status),
    )


def _today_activity(record: HealthRecord | None, prev_record: HealthRecord | None) -> ActivityMetric:
    activity = (record.activity or {}) if record else {}
    prev_activity = (prev_record.activity or {}) if prev_record else {}
    steps = activity.get("steps")
    prev_steps = prev_activity.get("steps")
    status = health_metrics.activity_status(steps)
    return ActivityMetric(
        steps=steps,
        calories=activity.get("calories"),
        active_minutes=None,
        status=_map_status(status),
        trend=_value_trend(steps, prev_steps),
    )


def _build_today_metrics(record: HealthRecord | None, prev_record: HealthRecord | None) -> HealthMetrics:
    return HealthMetrics(
        heart_rate=_today_heart_rate(record, prev_record),
        blood_pressure=_today_blood_pressure(record, prev_record),
        blood_oxygen=_today_blood_oxygen(record, prev_record),
        sleep=_today_sleep(record, prev_record),
        body_temperature=_today_body_temperature(record, prev_record),
        activity=_today_activity(record, prev_record),
    )


def _today_ai_insight(date_value: date_cls, score: int, level: str, diff: int, metrics: HealthMetrics) -> HealthInsight:
    prompt = (
        f"Analyze this user's wearable health data for {date_value.isoformat()} compared with yesterday.\n"
        f"Overall health score: {score}/100 ({level}). Change vs yesterday: {diff:+d}.\n"
        f"Metrics: {metrics.model_dump_json()}\n"
        "Return strictly a JSON object with exactly these keys:\n"
        '- "summary": 1-2 sentence overall health summary comparing today with yesterday\n'
        '- "highlights": array of 2-4 {"type","metric","title","description"} objects, '
        "type one of positive/warning/risk/info, metric one of heart_rate/blood_pressure/blood_oxygen/"
        "sleep/body_temperature/activity\n"
    )
    try:
        ai = generate_daily(prompt)
    except Exception:
        logger.exception("Dashboard today AI insight generation failed")
        return HealthInsight(is_available=False, summary=None, highlights=[])

    highlights = [HealthHighlight(**h) for h in ai.get("highlights", [])]
    return HealthInsight(is_available=True, summary=ai.get("summary", ""), highlights=highlights)


def _build_today_overview(db: Session, device: Device, today: date_cls) -> TodayHealthOverview:
    yesterday = today - timedelta(days=1)
    record = (
        db.query(HealthRecord).filter(HealthRecord.device_id == device.id, HealthRecord.date == today).first()
    )
    prev_record = (
        db.query(HealthRecord).filter(HealthRecord.device_id == device.id, HealthRecord.date == yesterday).first()
    )

    today_ok = _has_data(record)
    yesterday_ok = _has_data(prev_record)
    metrics = _build_today_metrics(record, prev_record)

    if not today_ok and not yesterday_ok:
        data_status = "no_data"
    elif today_ok and yesterday_ok:
        data_status = "sufficient"
    else:
        data_status = "insufficient"

    if data_status != "sufficient":
        return TodayHealthOverview(
            date=today.isoformat(),
            data_status=data_status,
            message=_INSUFFICIENT_MESSAGES["today"],
            health_score=HealthScore(score=None, level="unknown", summary=None),
            health_trend=HealthTrend(
                compare_with="yesterday", trend="insufficient_data", score_change=None, summary=None
            ),
            health_insight=HealthInsight(is_available=False, summary=None, highlights=[]),
            metrics=metrics,
        )

    score = _record_score(record)
    level = health_metrics.level_from_score(score)
    prev_score = _record_score(prev_record)
    diff = score - prev_score
    trend = _score_trend(diff)
    mapped_level = _map_level(level)

    health_score = HealthScore(score=score, level=mapped_level, summary=f"Today's overall health condition is {mapped_level}.")
    health_trend = HealthTrend(
        compare_with="yesterday",
        trend=trend,
        score_change=diff,
        summary=(
            f"Today's health score {'increased' if diff > 0 else 'decreased' if diff < 0 else 'stayed the same'} "
            f"by {abs(diff)} points compared with yesterday."
        ),
    )
    health_insight = _today_ai_insight(today, score, level, diff, metrics)

    return TodayHealthOverview(
        date=today.isoformat(),
        data_status="sufficient",
        message=None,
        health_score=health_score,
        health_trend=health_trend,
        health_insight=health_insight,
        metrics=metrics,
    )


# ---- weekly metrics ----


def _weekly_heart_rate(records: list[HealthRecord]) -> WeeklyHeartRateMetric:
    weekly_avg = _avg([average_heart_rate(r) for r in records])
    status = health_metrics.heart_rate_status(weekly_avg)
    first, second = _half_split(records)
    first_status = health_metrics.heart_rate_status(_avg([average_heart_rate(r) for r in first]))
    second_status = health_metrics.heart_rate_status(_avg([average_heart_rate(r) for r in second]))
    return WeeklyHeartRateMetric(
        weekly_avg=round(weekly_avg, 1) if weekly_avg is not None else None,
        status=_map_status(status),
        trend=_status_trend(second_status, first_status),
    )


def _weekly_blood_pressure(records: list[HealthRecord]) -> WeeklyBloodPressureMetric:
    avg_sys = _avg([(r.blood_pressure or {}).get("systolic") for r in records])
    avg_dia = _avg([(r.blood_pressure or {}).get("diastolic") for r in records])
    status = health_metrics.blood_pressure_status(avg_sys, avg_dia)
    first, second = _half_split(records)
    first_status = health_metrics.blood_pressure_status(
        _avg([(r.blood_pressure or {}).get("systolic") for r in first]),
        _avg([(r.blood_pressure or {}).get("diastolic") for r in first]),
    )
    second_status = health_metrics.blood_pressure_status(
        _avg([(r.blood_pressure or {}).get("systolic") for r in second]),
        _avg([(r.blood_pressure or {}).get("diastolic") for r in second]),
    )
    return WeeklyBloodPressureMetric(
        avg_systolic=round(avg_sys) if avg_sys is not None else None,
        avg_diastolic=round(avg_dia) if avg_dia is not None else None,
        status=_map_status(status),
        trend=_status_trend(second_status, first_status),
    )


def _weekly_blood_oxygen(records: list[HealthRecord]) -> WeeklyBloodOxygenMetric:
    values = [v for v in ((r.blood_oxygen or {}).get("value") for r in records) if v is not None]
    weekly_avg = _avg(values)
    status = health_metrics.blood_oxygen_status(weekly_avg)
    first, second = _half_split(records)
    first_avg = _avg([(r.blood_oxygen or {}).get("value") for r in first])
    second_avg = _avg([(r.blood_oxygen or {}).get("value") for r in second])
    return WeeklyBloodOxygenMetric(
        weekly_avg=round(weekly_avg) if weekly_avg is not None else None,
        min=round(min(values)) if values else None,
        status=_map_status(status),
        trend=_status_trend(
            health_metrics.blood_oxygen_status(second_avg), health_metrics.blood_oxygen_status(first_avg)
        ),
    )


def _weekly_sleep(records: list[HealthRecord]) -> WeeklySleepMetric:
    avg_total = _avg([(r.sleep or {}).get("total") for r in records])
    quality_scores = [q for q in (_sleep_quality_score(r.sleep) for r in records) if q is not None]
    avg_quality = round(_avg(quality_scores)) if quality_scores else None
    status = health_metrics.sleep_status(avg_total)
    first, second = _half_split(records)
    first_avg = _avg([(r.sleep or {}).get("total") for r in first])
    second_avg = _avg([(r.sleep or {}).get("total") for r in second])
    return WeeklySleepMetric(
        avg_duration=round(avg_total / 60, 1) if avg_total is not None else None,
        avg_quality_score=avg_quality,
        status=_map_status(status),
        trend=_value_trend(second_avg, first_avg),
    )


def _weekly_body_temperature(records: list[HealthRecord]) -> WeeklyBodyTemperatureMetric:
    values = [v for v in ((r.body_temperature or {}).get("value") for r in records) if v is not None]
    weekly_avg = _avg(values)
    status = health_metrics.body_temperature_status(weekly_avg)
    first, second = _half_split(records)
    first_avg = _avg([(r.body_temperature or {}).get("value") for r in first])
    second_avg = _avg([(r.body_temperature or {}).get("value") for r in second])
    return WeeklyBodyTemperatureMetric(
        weekly_avg=round(weekly_avg, 1) if weekly_avg is not None else None,
        status=_map_status(status),
        trend=_status_trend(
            health_metrics.body_temperature_status(second_avg), health_metrics.body_temperature_status(first_avg)
        ),
    )


def _weekly_activity(records: list[HealthRecord]) -> WeeklyActivityMetric:
    avg_steps = _avg([(r.activity or {}).get("steps") for r in records])
    avg_calories = _avg([(r.activity or {}).get("calories") for r in records])
    status = health_metrics.activity_status(avg_steps)
    first, second = _half_split(records)
    first_avg = _avg([(r.activity or {}).get("steps") for r in first])
    second_avg = _avg([(r.activity or {}).get("steps") for r in second])
    return WeeklyActivityMetric(
        avg_steps=round(avg_steps) if avg_steps is not None else None,
        avg_calories=round(avg_calories) if avg_calories is not None else None,
        avg_active_minutes=None,
        status=_map_status(status),
        trend=_value_trend(second_avg, first_avg),
    )


def _build_weekly_metrics(records: list[HealthRecord]) -> WeeklyHealthMetrics:
    return WeeklyHealthMetrics(
        heart_rate=_weekly_heart_rate(records),
        blood_pressure=_weekly_blood_pressure(records),
        blood_oxygen=_weekly_blood_oxygen(records),
        sleep=_weekly_sleep(records),
        body_temperature=_weekly_body_temperature(records),
        activity=_weekly_activity(records),
    )


def _weekly_ai_insight(
    start_date: date_cls, end_date: date_cls, score: int, level: str, diff: int, metrics: WeeklyHealthMetrics
) -> HealthInsight:
    prompt = (
        f"Analyze this user's weekly wearable health report for {start_date.isoformat()} to {end_date.isoformat()}.\n"
        f"Weekly average health score: {score}/100 ({level}). Change across the week: {diff:+d}.\n"
        f"Metrics: {metrics.model_dump_json()}\n"
        "Return strictly a JSON object with exactly these keys:\n"
        '- "summary": 1-2 sentence overall weekly health summary\n'
        '- "highlights": array of 2-4 {"type","metric","title","description"} objects, '
        "type one of positive/warning/risk/info, metric one of heart_rate/blood_pressure/blood_oxygen/"
        "sleep/body_temperature/activity\n"
    )
    try:
        ai = generate_periodic(prompt)
    except Exception:
        logger.exception("Dashboard weekly AI insight generation failed")
        return HealthInsight(is_available=False, summary=None, highlights=[])

    highlights = [HealthHighlight(**h) for h in ai.get("highlights", [])]
    return HealthInsight(is_available=True, summary=ai.get("summary", ""), highlights=highlights)


def _build_weekly_overview(db: Session, device: Device, today: date_cls) -> WeeklyHealthOverview:
    start_date = today - timedelta(days=6)
    records = (
        db.query(HealthRecord)
        .filter(HealthRecord.device_id == device.id, HealthRecord.date >= start_date, HealthRecord.date <= today)
        .order_by(HealthRecord.date.asc())
        .all()
    )
    days_with_data = [r for r in records if _has_data(r)]
    metrics = _build_weekly_metrics(records)

    if not days_with_data:
        data_status = "no_data"
    elif len(days_with_data) < _MIN_WEEKLY_DAYS:
        data_status = "insufficient"
    else:
        data_status = "sufficient"

    if data_status != "sufficient":
        return WeeklyHealthOverview(
            start_date=start_date.isoformat(),
            end_date=today.isoformat(),
            data_status=data_status,
            message=_INSUFFICIENT_MESSAGES["weekly"],
            health_score=HealthScore(avg_score=None, level="unknown", summary=None),
            health_trend=HealthTrend(
                compare_with="latest_7_days", trend="insufficient_data", score_change=None, summary=None
            ),
            health_insight=HealthInsight(is_available=False, summary=None, highlights=[]),
            metrics=metrics,
        )

    scores = [_record_score(r) for r in days_with_data]
    avg_score = round(sum(scores) / len(scores))
    level = health_metrics.level_from_score(avg_score)
    mapped_level = _map_level(level)

    first, second = _half_split(days_with_data)
    first_avg = round(sum(_record_score(r) for r in first) / len(first))
    second_avg = round(sum(_record_score(r) for r in second) / len(second))
    diff = second_avg - first_avg
    trend = _score_trend(diff)

    health_score = HealthScore(
        avg_score=avg_score, level=mapped_level, summary=f"This week's overall health condition is {mapped_level}."
    )
    health_trend = HealthTrend(
        compare_with="latest_7_days",
        trend=trend,
        score_change=diff,
        summary=(
            f"The weekly health condition {'improved' if diff > 0 else 'declined' if diff < 0 else 'remained stable'} "
            "based on the latest 7 days of data."
        ),
    )
    health_insight = _weekly_ai_insight(start_date, today, avg_score, level, diff, metrics)

    return WeeklyHealthOverview(
        start_date=start_date.isoformat(),
        end_date=today.isoformat(),
        data_status="sufficient",
        message=None,
        health_score=health_score,
        health_trend=health_trend,
        health_insight=health_insight,
        metrics=metrics,
    )


def get_dashboard(db: Session, device: Device) -> DashboardResponse:
    today = _today()
    today_overview = _build_today_overview(db, device, today)
    weekly_overview = _build_weekly_overview(db, device, today)

    return DashboardResponse(
        success=True,
        data=DashboardData(
            today_health_overview=today_overview,
            weekly_health_overview=weekly_overview,
            generated_at=datetime.now(timezone.utc),
        ),
        message="Dashboard data retrieved successfully.",
    )
