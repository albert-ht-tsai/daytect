from datetime import date as date_cls
from datetime import datetime, timedelta, timezone

from sqlalchemy.orm import Session

from src.core.ai_client import generate_daily, generate_periodic
from src.core.logging import logger
from src.dashboard.schemas.dashboard_schema import (
    BloodComponentsMetric,
    BloodOxygenMetric,
    BloodPressureMetric,
    BloodPressureRecord,
    BodyTemperatureMetric,
    DashboardData,
    DashboardResponse,
    EcgMetric,
    HealthDataTimeline,
    HealthHighlight,
    HealthInsight,
    HealthMetrics,
    HealthScore,
    HealthTrend,
    HeartRateMetric,
    HrvMetric,
    MetMetric,
    SleepMetric,
    SleepRecord,
    StressMetric,
    StressRecord,
    TodayHealthOverview,
    ValueTimeRecord,
    WeeklyBloodComponentsMetric,
    WeeklyBloodOxygenMetric,
    WeeklyBloodPressureMetric,
    WeeklyBodyTemperatureMetric,
    WeeklyEcgMetric,
    WeeklyHealthMetrics,
    WeeklyHealthOverview,
    WeeklyHeartRateMetric,
    WeeklyHrvMetric,
    WeeklyMetMetric,
    WeeklySleepMetric,
    WeeklyStressMetric,
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
_DATA_FIELDS = (
    "heart_rate",
    "blood_pressure",
    "blood_oxygen",
    "sleep",
    "body_temperature",
    "hrv",
    "ecg",
    "stress",
    "activity",
    "blood_components",
)


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


def _record_score(record: HealthRecord) -> int:
    score, _ = health_metrics.compute_health_score(compute_metric_statuses(record))
    return score


# ---- today metrics ----


def _today_heart_rate(record: HealthRecord | None, prev_record: HealthRecord | None) -> HeartRateMetric | None:
    readings = sorted((record.heart_rate or []), key=lambda r: r["time"]) if record else []
    if not readings:
        return None
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


def _today_blood_pressure(record: HealthRecord | None, prev_record: HealthRecord | None) -> BloodPressureMetric | None:
    bp = (record.blood_pressure or {}) if record else {}
    if not bp.get("systolic") and not bp.get("diastolic"):
        return None
    prev_bp = (prev_record.blood_pressure or {}) if prev_record else {}
    status = health_metrics.blood_pressure_status(bp.get("systolic"), bp.get("diastolic"))
    prev_status = health_metrics.blood_pressure_status(prev_bp.get("systolic"), prev_bp.get("diastolic"))
    return BloodPressureMetric(
        systolic=bp.get("systolic"),
        diastolic=bp.get("diastolic"),
        status=_map_status(status),
        trend=_status_trend(status, prev_status),
    )


def _today_blood_oxygen(record: HealthRecord | None, prev_record: HealthRecord | None) -> BloodOxygenMetric | None:
    spo2 = (record.blood_oxygen or {}).get("value") if record else None
    if spo2 is None:
        return None
    prev_spo2 = (prev_record.blood_oxygen or {}).get("value") if prev_record else None
    status = health_metrics.blood_oxygen_status(spo2)
    prev_status = health_metrics.blood_oxygen_status(prev_spo2)
    return BloodOxygenMetric(
        avg=spo2,
        min=spo2,
        status=_map_status(status),
        trend=_status_trend(status, prev_status),
    )


def _today_sleep(record: HealthRecord | None, prev_record: HealthRecord | None) -> SleepMetric | None:
    sleep = (record.sleep or {}) if record else {}
    if not sleep:
        return None
    prev_sleep = (prev_record.sleep or {}) if prev_record else {}
    total = sleep.get("total")
    prev_total = prev_sleep.get("total")
    status = health_metrics.sleep_status(total)
    return SleepMetric(
        light=sleep.get("light"),
        deep=sleep.get("deep"),
        wake=sleep.get("wake"),
        total=total,
        quality=sleep.get("quality"),
        status=_map_status(status),
        trend=_value_trend(total, prev_total),
    )


def _today_body_temperature(record: HealthRecord | None, prev_record: HealthRecord | None) -> BodyTemperatureMetric | None:
    temp = (record.body_temperature or {}).get("value") if record else None
    if temp is None:
        return None
    prev_temp = (prev_record.body_temperature or {}).get("value") if prev_record else None
    status = health_metrics.body_temperature_status(temp)
    prev_status = health_metrics.body_temperature_status(prev_temp)
    return BodyTemperatureMetric(
        avg=temp,
        status=_map_status(status),
        trend=_status_trend(status, prev_status),
    )


def _today_hrv(record: HealthRecord | None, prev_record: HealthRecord | None) -> HrvMetric | None:
    hrv_value = (record.hrv or {}).get("value") if record else None
    if hrv_value is None:
        return None
    prev_hrv = (prev_record.hrv or {}).get("value") if prev_record else None
    status = health_metrics.hrv_status(hrv_value)
    prev_status = health_metrics.hrv_status(prev_hrv)
    return HrvMetric(
        avg=hrv_value,
        status=_map_status(status),
        trend=_status_trend(status, prev_status),
    )


def _today_ecg(record: HealthRecord | None, prev_record: HealthRecord | None) -> EcgMetric | None:
    ecg = (record.ecg or {}) if record else {}
    if not ecg:
        return None
    ecg_status = ecg.get("status")
    mapped = ecg_status if ecg_status in ("normal", "good", "low", "high", "abnormal") else "unknown"
    prev_ecg = (prev_record.ecg or {}) if prev_record else {}
    prev_ecg_status = prev_ecg.get("status") if prev_ecg else None
    prev_mapped = prev_ecg_status if prev_ecg_status in ("normal", "good", "low", "high", "abnormal") else "unknown"
    return EcgMetric(
        status=mapped,
        trend=_status_trend(ecg_status, prev_ecg_status),
    )


def _today_met(record: HealthRecord | None, prev_record: HealthRecord | None) -> MetMetric | None:
    met_list = getattr(record, "met", None) or [] if record else []
    if not met_list:
        return None
    values = [r.get("value") for r in met_list if r.get("value") is not None]
    avg = _avg(values)
    prev_met = getattr(prev_record, "met", None) or [] if prev_record else []
    prev_values = [r.get("value") for r in prev_met if r.get("value") is not None]
    prev_avg = _avg(prev_values)
    return MetMetric(
        avg=round(avg, 1) if avg is not None else None,
        status="normal",
        trend=_value_trend(avg, prev_avg),
    )


def _today_stress(record: HealthRecord | None, prev_record: HealthRecord | None) -> StressMetric | None:
    stress = (record.stress or {}) if record else {}
    if not stress:
        return None
    stress_value = stress.get("value")
    prev_stress = (prev_record.stress or {}) if prev_record else {}
    prev_value = prev_stress.get("value")
    return StressMetric(
        avg=stress_value,
        status="normal" if stress_value is not None else "unknown",
        trend=_value_trend(stress_value, prev_value),
    )


def _today_blood_components(record: HealthRecord | None, prev_record: HealthRecord | None) -> BloodComponentsMetric | None:
    bc = (record.blood_components or {}) if record else {}
    if not bc:
        return None
    prev_bc = (prev_record.blood_components or {}) if prev_record else {}
    return BloodComponentsMetric(
        status="normal",
        trend="stable" if prev_bc else "insufficient_data",
    )


def _build_today_metrics(record: HealthRecord | None, prev_record: HealthRecord | None) -> HealthMetrics:
    return HealthMetrics(
        sleep=_today_sleep(record, prev_record),
        heart_rate=_today_heart_rate(record, prev_record),
        blood_pressure=_today_blood_pressure(record, prev_record),
        blood_oxygen=_today_blood_oxygen(record, prev_record),
        body_temperature=_today_body_temperature(record, prev_record),
        hrv=_today_hrv(record, prev_record),
        ecg=_today_ecg(record, prev_record),
        met=_today_met(record, prev_record),
        stress=_today_stress(record, prev_record),
        blood_components=_today_blood_components(record, prev_record),
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
        "sleep/body_temperature/hrv/ecg/met/stress/blood_components\n"
    )
    try:
        ai = generate_daily(prompt)
    except Exception:
        logger.exception("Dashboard today AI insight generation failed")
        return HealthInsight(is_available=False, summary=None, highlights=[])

    highlights = [HealthHighlight(**h) for h in ai.get("highlights", [])]
    return HealthInsight(is_available=True, summary=ai.get("summary", ""), highlights=highlights)


def _build_today_health_data(record: HealthRecord | None) -> HealthDataTimeline:
    if record is None:
        return HealthDataTimeline()

    recorded_at_str = record.recorded_at.isoformat() if record.recorded_at else ""

    sleep_records: list[SleepRecord] = []
    if record.sleep:
        s = record.sleep
        sleep_records.append(SleepRecord(
            date=record.date.isoformat() if record.date else None,
            start_time=s.get("start_time") or recorded_at_str or None,
            end_time=s.get("end_time"),
            light=s.get("light"),
            deep=s.get("deep"),
            wake=s.get("wake"),
            total=s.get("total"),
            quality=s.get("quality"),
        ))

    heart_rate_records = [
        ValueTimeRecord(value=r["value"], unit=r.get("unit", "bpm"), time=r["time"])
        for r in sorted(record.heart_rate or [], key=lambda x: x["time"])
    ]

    bp_records: list[BloodPressureRecord] = []
    if record.blood_pressure:
        bp = record.blood_pressure
        bp_records.append(BloodPressureRecord(
            systolic=bp.get("systolic"),
            diastolic=bp.get("diastolic"),
            time=recorded_at_str,
        ))

    spo2_records: list[ValueTimeRecord] = []
    if record.blood_oxygen:
        spo2 = record.blood_oxygen
        spo2_records.append(ValueTimeRecord(value=spo2.get("value"), unit=spo2.get("unit", "%"), time=recorded_at_str))

    temp_records: list[ValueTimeRecord] = []
    if record.body_temperature:
        temp = record.body_temperature
        temp_records.append(ValueTimeRecord(value=temp.get("value"), unit=temp.get("unit", "°C"), time=recorded_at_str))

    hrv_records: list[ValueTimeRecord] = []
    if record.hrv:
        hrv = record.hrv
        hrv_records.append(ValueTimeRecord(value=hrv.get("value"), unit=hrv.get("unit", "ms"), time=recorded_at_str))

    ecg_records: list[ValueTimeRecord] = []
    if record.ecg:
        ecg = record.ecg
        ecg_records.append(ValueTimeRecord(
            value=ecg.get("status") or ecg.get("file_url"),
            unit="raw",
            time=recorded_at_str,
        ))

    met_records = [
        ValueTimeRecord(value=r.get("value"), unit=r.get("unit", "MET"), time=r.get("time", ""))
        for r in sorted(getattr(record, "met", None) or [], key=lambda x: x.get("time", ""))
    ]

    stress_records: list[StressRecord] = []
    if record.stress:
        stress = record.stress
        stress_records.append(StressRecord(
            value=stress.get("value"),
            unit="score",
            time=recorded_at_str,
        ))

    bc_records: list[ValueTimeRecord] = []
    if record.blood_components:
        bc_records.append(ValueTimeRecord(value=record.blood_components, unit="value", time=recorded_at_str))

    return HealthDataTimeline(
        sleep=sleep_records,
        heart_rate=heart_rate_records,
        blood_pressure=bp_records,
        blood_oxygen=spo2_records,
        body_temperature=temp_records,
        hrv=hrv_records,
        ecg=ecg_records,
        met=met_records,
        stress=stress_records,
        blood_components=bc_records,
    )


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
    health_data = _build_today_health_data(record)

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
            health_data=health_data,
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
        health_data=health_data,
    )


# ---- weekly metrics ----


def _weekly_heart_rate(records: list[HealthRecord]) -> WeeklyHeartRateMetric | None:
    avgs = [average_heart_rate(r) for r in records]
    weekly_avg = _avg(avgs)
    if weekly_avg is None:
        return None
    status = health_metrics.heart_rate_status(weekly_avg)
    first, second = _half_split(records)
    first_status = health_metrics.heart_rate_status(_avg([average_heart_rate(r) for r in first]))
    second_status = health_metrics.heart_rate_status(_avg([average_heart_rate(r) for r in second]))
    return WeeklyHeartRateMetric(
        weekly_avg=round(weekly_avg, 1),
        status=_map_status(status),
        trend=_status_trend(second_status, first_status),
    )


def _weekly_blood_pressure(records: list[HealthRecord]) -> WeeklyBloodPressureMetric | None:
    avg_sys = _avg([(r.blood_pressure or {}).get("systolic") for r in records])
    avg_dia = _avg([(r.blood_pressure or {}).get("diastolic") for r in records])
    if avg_sys is None and avg_dia is None:
        return None
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


def _weekly_blood_oxygen(records: list[HealthRecord]) -> WeeklyBloodOxygenMetric | None:
    values = [v for v in ((r.blood_oxygen or {}).get("value") for r in records) if v is not None]
    if not values:
        return None
    weekly_avg = _avg(values)
    status = health_metrics.blood_oxygen_status(weekly_avg)
    first, second = _half_split(records)
    first_avg = _avg([(r.blood_oxygen or {}).get("value") for r in first])
    second_avg = _avg([(r.blood_oxygen or {}).get("value") for r in second])
    return WeeklyBloodOxygenMetric(
        weekly_avg=round(weekly_avg) if weekly_avg is not None else None,
        min=round(min(values)),
        status=_map_status(status),
        trend=_status_trend(
            health_metrics.blood_oxygen_status(second_avg), health_metrics.blood_oxygen_status(first_avg)
        ),
    )


def _weekly_sleep(records: list[HealthRecord]) -> WeeklySleepMetric | None:
    sleeps = [r.sleep for r in records if r.sleep]
    if not sleeps:
        return None
    avg_total = _avg([s.get("total") for s in sleeps])
    avg_light = _avg([s.get("light") for s in sleeps])
    avg_deep = _avg([s.get("deep") for s in sleeps])
    avg_wake = _avg([s.get("wake") for s in sleeps])
    avg_quality = _avg([s.get("quality") for s in sleeps])
    status = health_metrics.sleep_status(avg_total)
    first, second = _half_split(records)
    first_avg = _avg([(r.sleep or {}).get("total") for r in first])
    second_avg = _avg([(r.sleep or {}).get("total") for r in second])
    return WeeklySleepMetric(
        avg_light=round(avg_light, 1) if avg_light is not None else None,
        avg_deep=round(avg_deep, 1) if avg_deep is not None else None,
        avg_wake=round(avg_wake, 1) if avg_wake is not None else None,
        avg_total=round(avg_total, 1) if avg_total is not None else None,
        avg_quality=round(avg_quality, 1) if avg_quality is not None else None,
        status=_map_status(status),
        trend=_value_trend(second_avg, first_avg),
    )


def _weekly_body_temperature(records: list[HealthRecord]) -> WeeklyBodyTemperatureMetric | None:
    values = [v for v in ((r.body_temperature or {}).get("value") for r in records) if v is not None]
    if not values:
        return None
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


def _weekly_hrv(records: list[HealthRecord]) -> WeeklyHrvMetric | None:
    values = [v for v in ((r.hrv or {}).get("value") for r in records) if v is not None]
    if not values:
        return None
    weekly_avg = _avg(values)
    status = health_metrics.hrv_status(weekly_avg)
    first, second = _half_split(records)
    first_avg = _avg([(r.hrv or {}).get("value") for r in first])
    second_avg = _avg([(r.hrv or {}).get("value") for r in second])
    return WeeklyHrvMetric(
        weekly_avg=round(weekly_avg, 1) if weekly_avg is not None else None,
        status=_map_status(status),
        trend=_status_trend(health_metrics.hrv_status(second_avg), health_metrics.hrv_status(first_avg)),
    )


def _weekly_ecg(records: list[HealthRecord]) -> WeeklyEcgMetric | None:
    ecg_list = [r.ecg for r in records if r.ecg]
    if not ecg_list:
        return None
    statuses = [e.get("status") for e in ecg_list]
    has_abnormal = any(s not in (None, "normal") for s in statuses)
    return WeeklyEcgMetric(
        status="abnormal" if has_abnormal else "normal",
        trend="stable",
    )


def _weekly_met(records: list[HealthRecord]) -> WeeklyMetMetric | None:
    all_values = [
        v.get("value")
        for r in records
        for v in (getattr(r, "met", None) or [])
        if v.get("value") is not None
    ]
    if not all_values:
        return None
    weekly_avg = _avg(all_values)
    first, second = _half_split(records)
    first_values = [v.get("value") for r in first for v in (getattr(r, "met", None) or []) if v.get("value") is not None]
    second_values = [v.get("value") for r in second for v in (getattr(r, "met", None) or []) if v.get("value") is not None]
    return WeeklyMetMetric(
        weekly_avg=round(weekly_avg, 1) if weekly_avg is not None else None,
        status="normal",
        trend=_value_trend(_avg(second_values), _avg(first_values)),
    )


def _weekly_stress(records: list[HealthRecord]) -> WeeklyStressMetric | None:
    values = [v for v in ((r.stress or {}).get("value") for r in records) if v is not None]
    if not values:
        return None
    weekly_avg = _avg(values)
    first, second = _half_split(records)
    first_avg = _avg([(r.stress or {}).get("value") for r in first])
    second_avg = _avg([(r.stress or {}).get("value") for r in second])
    return WeeklyStressMetric(
        weekly_avg=round(weekly_avg, 1) if weekly_avg is not None else None,
        status="normal",
        trend=_value_trend(second_avg, first_avg),
    )


def _weekly_blood_components(records: list[HealthRecord]) -> WeeklyBloodComponentsMetric | None:
    if not any(r.blood_components for r in records):
        return None
    return WeeklyBloodComponentsMetric(
        status="normal",
        trend="stable",
    )


def _build_weekly_metrics(records: list[HealthRecord]) -> WeeklyHealthMetrics:
    return WeeklyHealthMetrics(
        sleep=_weekly_sleep(records),
        heart_rate=_weekly_heart_rate(records),
        blood_pressure=_weekly_blood_pressure(records),
        blood_oxygen=_weekly_blood_oxygen(records),
        body_temperature=_weekly_body_temperature(records),
        hrv=_weekly_hrv(records),
        ecg=_weekly_ecg(records),
        met=_weekly_met(records),
        stress=_weekly_stress(records),
        blood_components=_weekly_blood_components(records),
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
        "sleep/body_temperature/hrv/ecg/met/stress/blood_components\n"
    )
    try:
        ai = generate_periodic(prompt)
    except Exception:
        logger.exception("Dashboard weekly AI insight generation failed")
        return HealthInsight(is_available=False, summary=None, highlights=[])

    highlights = [HealthHighlight(**h) for h in ai.get("highlights", [])]
    return HealthInsight(is_available=True, summary=ai.get("summary", ""), highlights=highlights)


def _build_weekly_health_data(records: list[HealthRecord]) -> HealthDataTimeline:
    sleep_records: list[SleepRecord] = []
    heart_rate_records: list[ValueTimeRecord] = []
    bp_records: list[BloodPressureRecord] = []
    spo2_records: list[ValueTimeRecord] = []
    temp_records: list[ValueTimeRecord] = []
    hrv_records: list[ValueTimeRecord] = []
    ecg_records: list[ValueTimeRecord] = []
    met_records: list[ValueTimeRecord] = []
    stress_records: list[StressRecord] = []
    bc_records: list[ValueTimeRecord] = []

    for record in records:
        recorded_at_str = record.recorded_at.isoformat() if record.recorded_at else ""
        date_str = record.date.isoformat() if record.date else None

        if record.sleep:
            s = record.sleep
            sleep_records.append(SleepRecord(
                date=date_str,
                start_time=s.get("start_time"),
                end_time=s.get("end_time"),
                light=s.get("light"),
                deep=s.get("deep"),
                wake=s.get("wake"),
                total=s.get("total"),
                quality=s.get("quality"),
            ))

        for r in (record.heart_rate or []):
            heart_rate_records.append(ValueTimeRecord(value=r["value"], unit=r.get("unit", "bpm"), time=r["time"]))

        if record.blood_pressure:
            bp = record.blood_pressure
            bp_records.append(BloodPressureRecord(
                systolic=bp.get("systolic"),
                diastolic=bp.get("diastolic"),
                time=recorded_at_str,
            ))

        if record.blood_oxygen:
            spo2 = record.blood_oxygen
            spo2_records.append(ValueTimeRecord(value=spo2.get("value"), unit=spo2.get("unit", "%"), time=recorded_at_str))

        if record.body_temperature:
            temp = record.body_temperature
            temp_records.append(ValueTimeRecord(value=temp.get("value"), unit=temp.get("unit", "°C"), time=recorded_at_str))

        if record.hrv:
            hrv = record.hrv
            hrv_records.append(ValueTimeRecord(value=hrv.get("value"), unit=hrv.get("unit", "ms"), time=recorded_at_str))

        if record.ecg:
            ecg = record.ecg
            ecg_records.append(ValueTimeRecord(
                value=ecg.get("status") or ecg.get("file_url"),
                unit="raw",
                time=recorded_at_str,
            ))

        for r in (getattr(record, "met", None) or []):
            met_records.append(ValueTimeRecord(value=r.get("value"), unit=r.get("unit", "MET"), time=r.get("time", "")))

        if record.stress:
            stress = record.stress
            stress_records.append(StressRecord(
                value=stress.get("value"),
                unit="score",
                time=recorded_at_str,
            ))

        if record.blood_components:
            bc_records.append(ValueTimeRecord(value=record.blood_components, unit="value", time=recorded_at_str))

    heart_rate_records.sort(key=lambda x: x.time)
    bp_records.sort(key=lambda x: x.time)
    spo2_records.sort(key=lambda x: x.time)
    temp_records.sort(key=lambda x: x.time)
    hrv_records.sort(key=lambda x: x.time)
    ecg_records.sort(key=lambda x: x.time)
    met_records.sort(key=lambda x: x.time)
    stress_records.sort(key=lambda x: x.time)
    bc_records.sort(key=lambda x: x.time)

    return HealthDataTimeline(
        sleep=sleep_records,
        heart_rate=heart_rate_records,
        blood_pressure=bp_records,
        blood_oxygen=spo2_records,
        body_temperature=temp_records,
        hrv=hrv_records,
        ecg=ecg_records,
        met=met_records,
        stress=stress_records,
        blood_components=bc_records,
    )


def _build_weekly_overview(db: Session, device: Device, today: date_cls) -> WeeklyHealthOverview:
    start_date = today - timedelta(days=6)
    records = (
        db.query(HealthRecord)
        .filter(HealthRecord.device_id == device.id, HealthRecord.date >= start_date, HealthRecord.date <= today)
        .order_by(HealthRecord.date.asc())
        .all()
    )
    days_with_data = [r for r in records if _has_data(r)]
    metrics = _build_weekly_metrics(days_with_data)
    health_data = _build_weekly_health_data(records)

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
            health_data=health_data,
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
        health_data=health_data,
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
