"""Pure, DB-free statistics layer for health reports: period-date math and turning raw
SleepRecord/HealthRecord/ActivityRecord rows into the fixed-structure numbers the report needs
(averages, day-over-day comparisons, 0-100 scores, deterministic status labels). No AI call and
no DB session here — see health_report_service.py for orchestration and the AI narrative step.

Per the requirement doc: "數值、狀態及比較結果應由後端計算，不應交給 AI 運算" — everything in this
file is deterministic arithmetic over already-uploaded per-day averages (device data is uploaded
as one averaged value per day, not raw per-sample readings — see HealthAvgRecordPayload), never an
AI call.
"""

import math
from datetime import date, datetime, timedelta, timezone

from src.core import health_scoring
from src.device.models.activity_model import ActivityRecord
from src.device.models.device_model import DeviceRecord
from src.device.models.health_model import HealthRecord
from src.device.models.sleep_model import SleepRecord

PERIOD_DAYS = 7

# No per-user/per-device timezone is stored anywhere in this codebase — matches the same fixed
# +08:00 convention used elsewhere (see assistant/services/question_summary_service.py's
# REPORT_TZ). Not configurable per request; removed the earlier IANA-timezone-name design so this
# module has no zoneinfo/tzdata dependency.
REPORT_TZ = timezone(timedelta(hours=8))

# Universally-cited clinical reference ranges (not this codebase's own invention, unlike the
# finer-grained scoring bands in health_scoring.py) — kept to just the two metrics where a single
# widely-agreed "normal range" exists, per the plan's decision not to fabricate bands for metrics
# (stress, HRV, MET, respiratory rate) that don't have one universally-agreed pair of numbers.
_HEART_RATE_REFERENCE = (60, 100)
_BLOOD_OXYGEN_REFERENCE = (95, 100)


class InvalidReportDateError(ValueError):
    """Raised by compute_period for a malformed or future `date` (the anchor the caller wants the
    7-day period to end on)."""


# ---------------------------------------------------------------------------
# Period math
# ---------------------------------------------------------------------------

def compute_period(anchor_date: str | None = None, now: datetime | None = None) -> dict:
    """The 7-day period ending on `anchor_date` (inclusive), plus the preceding 7-day comparison
    window, in the fixed REPORT_TZ. When `anchor_date` is omitted, defaults to "yesterday" (the
    original fixed-period behavior) so existing callers are unaffected.

    Raises InvalidReportDateError for a malformed `anchor_date` string or one that falls after
    "today" in REPORT_TZ (no device data can exist for a future date)."""
    local_now = (now or datetime.now(REPORT_TZ)).astimezone(REPORT_TZ)
    today = local_now.date()

    if anchor_date is not None:
        try:
            period_end = date.fromisoformat(anchor_date)
        except ValueError as e:
            raise InvalidReportDateError(f"Invalid date: {anchor_date}") from e
        if period_end > today:
            raise InvalidReportDateError(f"date cannot be in the future: {anchor_date}")
    else:
        period_end = today - timedelta(days=1)

    period_start = period_end - timedelta(days=PERIOD_DAYS - 1)
    comparison_end = period_start - timedelta(days=1)
    comparison_start = comparison_end - timedelta(days=PERIOD_DAYS - 1)

    return {
        "period_start": period_start.isoformat(),
        "period_end": period_end.isoformat(),
        "comparison_start": comparison_start.isoformat(),
        "comparison_end": comparison_end.isoformat(),
    }


def date_range(start: str, end: str) -> list[str]:
    start_d = date.fromisoformat(start)
    end_d = date.fromisoformat(end)
    days = (end_d - start_d).days + 1
    return [(start_d + timedelta(days=i)).isoformat() for i in range(days)]


# ---------------------------------------------------------------------------
# Small numeric helpers
# ---------------------------------------------------------------------------

def _avg(values: list[float | None]) -> float | None:
    present = [v for v in values if v is not None]
    if not present:
        return None
    return sum(present) / len(present)


def _round(value: float | None, digits: int = 1) -> float | None:
    return None if value is None else round(value, digits)


def _change(current: float | None, previous: float | None) -> dict:
    """Plain numeric delta — direction is purely arithmetic (up/down/stable), NOT a judgement of
    better/worse (e.g. resting heart rate going "up" is usually unfavorable). Callers that need a
    favorable/unfavorable read must interpret `direction` themselves per metric."""
    if current is None or previous is None:
        return {"value": None, "percentage": None, "direction": "stable"}
    value = current - previous
    percentage = None if previous == 0 else round(value / previous * 100, 1)
    direction = "stable" if abs(value) < 1e-9 else ("up" if value > 0 else "down")
    return {"value": _round(value, 2), "percentage": percentage, "direction": direction}


def _metric_status_from_score(score: int | None) -> str:
    if score is None:
        return "insufficient_data"
    if score >= 85:
        return "normal"
    if score >= 60:
        return "attention"
    return "abnormal"


def _category_status_from_score(score: float | None, trend_direction: str | None) -> str:
    if score is None:
        return "insufficient_data"
    if trend_direction == "up" and score >= 60:
        return "improving"
    if score >= 85:
        return "good"
    if score >= 65:
        return "attention"
    return "abnormal"


# ---------------------------------------------------------------------------
# Sleep
# ---------------------------------------------------------------------------

def _time_to_minutes(iso_str: str | None) -> float | None:
    if not iso_str:
        return None
    try:
        dt = datetime.fromisoformat(iso_str)
    except ValueError:
        return None
    return dt.hour * 60 + dt.minute


def _circular_mean_minutes(minutes: list[float | None]) -> float | None:
    present = [m for m in minutes if m is not None]
    if not present:
        return None
    angles = [m / 1440 * 2 * math.pi for m in present]
    sin_sum = sum(math.sin(a) for a in angles)
    cos_sum = sum(math.cos(a) for a in angles)
    mean_angle = math.atan2(sin_sum, cos_sum)
    return (mean_angle / (2 * math.pi) * 1440) % 1440


def _circular_regularity_score(minutes: list[float | None]) -> int | None:
    """0-100 heuristic: tighter clustering of bedtime across the week -> higher score. Not a
    clinical measure — a simple circular-standard-deviation-based proxy for "how consistent was
    the user's bedtime", documented as such rather than presented as a device-measured metric."""
    present = [m for m in minutes if m is not None]
    if len(present) < 2:
        return None
    angles = [m / 1440 * 2 * math.pi for m in present]
    sin_sum = sum(math.sin(a) for a in angles)
    cos_sum = sum(math.cos(a) for a in angles)
    resultant = min(max(math.sqrt(sin_sum**2 + cos_sum**2) / len(present), 1e-9), 1.0)
    circular_std_minutes = math.sqrt(-2 * math.log(resultant)) / (2 * math.pi) * 1440
    return round(max(20, min(100, 100 - circular_std_minutes * 0.8)))


def _minutes_to_hhmm(minutes: float | None) -> str | None:
    if minutes is None:
        return None
    total = round(minutes) % 1440
    return f"{total // 60:02d}:{total % 60:02d}"


def _sleep_daily(dates: list[str], by_date: dict[str, SleepRecord]) -> list[dict]:
    daily = []
    for d in dates:
        record = by_date.get(d)
        summary = (record.sleep_summary or {}) if record else {}
        daily.append({
            "date": d,
            "total_sleep_minutes": summary.get("allSleepTime"),
            "deep_sleep_minutes": summary.get("deepSleepTime"),
            "light_sleep_minutes": summary.get("lowSleepTime"),
            "rem_sleep_minutes": summary.get("remSleepTime"),
            "wake_count": summary.get("wakeCount"),
            "sleep_down": summary.get("sleepDown"),
            "sleep_up": summary.get("sleepUp"),
            "score": summary.get("sleepQuality"),
        })
    return daily


def _sleep_summary(period_dates: list[str], comparison_dates: list[str], by_date: dict[str, SleepRecord]) -> dict:
    daily = _sleep_daily(period_dates, by_date)
    comparison_daily = _sleep_daily(comparison_dates, by_date)

    def col(rows: list[dict], key: str) -> list[float | None]:
        return [row[key] for row in rows]

    avg_total = _avg(col(daily, "total_sleep_minutes"))
    avg_deep = _avg(col(daily, "deep_sleep_minutes"))
    avg_light = _avg(col(daily, "light_sleep_minutes"))
    avg_rem = _avg(col(daily, "rem_sleep_minutes"))
    avg_wake_count = _avg(col(daily, "wake_count"))
    avg_quality = _avg(col(daily, "score"))

    comparison_avg_total = _avg(col(comparison_daily, "total_sleep_minutes"))
    comparison_avg_deep = _avg(col(comparison_daily, "deep_sleep_minutes"))
    comparison_avg_rem = _avg(col(comparison_daily, "rem_sleep_minutes"))
    comparison_avg_wake_count = _avg(col(comparison_daily, "wake_count"))

    bedtime_minutes = [_time_to_minutes(row["sleep_down"]) for row in daily]
    wake_minutes = [_time_to_minutes(row["sleep_up"]) for row in daily]

    deep_ratio = None if not avg_total else (avg_deep or 0) / avg_total * 100
    composite = health_scoring.score_sleep_composite(
        total_sleep_minutes=avg_total,
        deep_sleep_ratio_percent=deep_ratio,
        wake_count=avg_wake_count,
        # sleepQuality is on a different 0-100 device scale than the 1-5 grade this scorer
        # expects (see health_scoring.score_sleep_quality's docstring) — excluded, not converted.
        sleep_quality_level=None,
    )

    return {
        "average_total_sleep_minutes": _round(avg_total, 0),
        "average_deep_sleep_minutes": _round(avg_deep, 0),
        "average_light_sleep_minutes": _round(avg_light, 0),
        "average_rem_sleep_minutes": _round(avg_rem, 0),
        "average_wake_count": _round(avg_wake_count, 1),
        "average_bedtime": _minutes_to_hhmm(_circular_mean_minutes(bedtime_minutes)),
        "average_wake_time": _minutes_to_hhmm(_circular_mean_minutes(wake_minutes)),
        "sleep_regularity_score": _circular_regularity_score(bedtime_minutes),
        "change": {
            "total_sleep_minutes": _change(avg_total, comparison_avg_total)["value"],
            "deep_sleep_minutes": _change(avg_deep, comparison_avg_deep)["value"],
            "rem_sleep_minutes": _change(avg_rem, comparison_avg_rem)["value"],
            "wake_count": _change(avg_wake_count, comparison_avg_wake_count)["value"],
        },
        "daily": daily,
        "_composite_score": composite["composite"],
        "_quality_avg": avg_quality,
        "_total_change": _change(avg_total, comparison_avg_total),
    }


# ---------------------------------------------------------------------------
# Health (vitals)
# ---------------------------------------------------------------------------

def _get(data: dict | None, *path):
    node = data or {}
    for key in path:
        if not isinstance(node, dict):
            return None
        node = node.get(key)
    return node


_HEALTH_METRICS = [
    ("heart_rate", "平均心率", "bpm", ("heartRate", "ppgs"), health_scoring.score_heart_rate),
    ("blood_oxygen", "平均血氧", "%", ("bloodOxygen", "oxygens"), health_scoring.score_blood_oxygen),
    ("body_temperature", "平均體溫", "°C", ("bodyTemperature", "temperature"), health_scoring.score_temperature),
    ("hrv", "平均 HRV", "ms", ("hrv", "values"), health_scoring.score_hrv),
    ("stress", "平均壓力", "score", ("stress", "pressure"), health_scoring.score_stress),
    ("respiratory_rate", "平均呼吸率", "breaths/min", ("respiratory", "resRates"), None),
    ("met", "平均 MET", "MET", ("met", "values"), health_scoring.score_met),
]


def _health_daily_values(dates: list[str], by_date: dict[str, HealthRecord], path: tuple) -> list[float | None]:
    return [_get(by_date[d].data, *path) if d in by_date else None for d in dates]


def _health_summary(period_dates: list[str], comparison_dates: list[str], by_date: dict[str, HealthRecord]) -> dict:
    metrics = []
    scores_for_category: list[int] = []

    for key, label, unit, path, scorer in _HEALTH_METRICS:
        values = _health_daily_values(period_dates, by_date, path)
        comparison_values = _health_daily_values(comparison_dates, by_date, path)
        avg = _avg(values)
        comparison_avg = _avg(comparison_values)
        change = _change(avg, comparison_avg)
        present = [v for v in values if v is not None]
        score = scorer(avg) if scorer else None
        if score is not None:
            scores_for_category.append(score)
        entry = {
            "key": key,
            "label": label,
            "value": _round(avg, 1),
            "unit": unit,
            "status": _metric_status_from_score(score) if scorer else (
                "insufficient_data" if avg is None else "normal"
            ),
            "change_value": change["value"],
            "change_percentage": change["percentage"],
            "change_direction": change["direction"],
        }
        if present:
            entry["minimum"] = _round(min(present), 1)
            entry["maximum"] = _round(max(present), 1)
        if key == "heart_rate":
            entry["reference_min"], entry["reference_max"] = _HEART_RATE_REFERENCE
        if key == "blood_oxygen":
            entry["reference_min"], entry["reference_max"] = _BLOOD_OXYGEN_REFERENCE
        metrics.append(entry)

    # Blood pressure: two-valued metric, handled separately from the table above.
    systolic_values = _health_daily_values(period_dates, by_date, ("bloodPressure", "systolic"))
    diastolic_values = _health_daily_values(period_dates, by_date, ("bloodPressure", "diastolic"))
    comparison_systolic = _health_daily_values(comparison_dates, by_date, ("bloodPressure", "systolic"))
    comparison_diastolic = _health_daily_values(comparison_dates, by_date, ("bloodPressure", "diastolic"))
    avg_systolic, avg_diastolic = _avg(systolic_values), _avg(diastolic_values)
    comparison_avg_systolic, comparison_avg_diastolic = _avg(comparison_systolic), _avg(comparison_diastolic)
    bp_score = health_scoring.score_blood_pressure(avg_systolic, avg_diastolic)
    if bp_score is not None:
        scores_for_category.append(bp_score)
    systolic_change = _change(avg_systolic, comparison_avg_systolic)
    diastolic_change = _change(avg_diastolic, comparison_avg_diastolic)
    metrics.insert(1, {
        "key": "blood_pressure",
        "label": "平均血壓",
        "value": {"systolic": _round(avg_systolic, 0), "diastolic": _round(avg_diastolic, 0)},
        "unit": "mmHg",
        "status": _metric_status_from_score(bp_score),
        "change_value": {"systolic": systolic_change["value"], "diastolic": diastolic_change["value"]},
        "change_percentage": None,
        "change_direction": systolic_change["direction"],
    })

    category_score = round(sum(scores_for_category) / len(scores_for_category)) if scores_for_category else None
    return {
        "metrics": metrics,
        "_category_score": category_score,
    }


# ---------------------------------------------------------------------------
# Activity
# ---------------------------------------------------------------------------

def _activity_daily(dates: list[str], by_date: dict[str, ActivityRecord]) -> list[dict]:
    daily = []
    for d in dates:
        record = by_date.get(d)
        data = (record.data or {}) if record else {}
        daily.append({
            "date": d,
            "steps": data.get("stepValue"),
            "distance_km": data.get("disValue"),
            "calories_kcal": data.get("calValue"),
        })
    return daily


def _activity_summary(period_dates: list[str], comparison_dates: list[str], by_date: dict[str, ActivityRecord]) -> dict:
    daily = _activity_daily(period_dates, by_date)
    comparison_daily = _activity_daily(comparison_dates, by_date)

    def col(rows: list[dict], key: str) -> list[float | None]:
        return [row[key] for row in rows]

    avg_steps = _avg(col(daily, "steps"))
    avg_distance = _avg(col(daily, "distance_km"))
    avg_calories = _avg(col(daily, "calories_kcal"))
    comparison_avg_steps = _avg(col(comparison_daily, "steps"))
    comparison_avg_distance = _avg(col(comparison_daily, "distance_km"))
    comparison_avg_calories = _avg(col(comparison_daily, "calories_kcal"))

    steps_present = [v for v in col(daily, "steps") if v is not None]
    distance_present = [v for v in col(daily, "distance_km") if v is not None]
    calories_present = [v for v in col(daily, "calories_kcal") if v is not None]

    steps_change = _change(avg_steps, comparison_avg_steps)
    distance_change = _change(avg_distance, comparison_avg_distance)
    calories_change = _change(avg_calories, comparison_avg_calories)

    # No clinical/medical reference table exists for daily steps/distance/calories (unlike heart
    # rate or blood oxygen) — per the plan, the activity category score is trend-based (how much
    # the period improved vs the comparison period) rather than an invented fixed 0-100 band.
    pct_changes = [c["percentage"] for c in (steps_change, distance_change, calories_change) if c["percentage"] is not None]
    if pct_changes and avg_steps is not None:
        trend_score = round(max(0, min(100, 70 + _avg(pct_changes))))
    else:
        trend_score = None

    return {
        "average_steps": _round(avg_steps, 0),
        "average_distance_km": _round(avg_distance, 1),
        "average_calories_kcal": _round(avg_calories, 0),
        "total_steps": _round(sum(steps_present), 0) if steps_present else None,
        "total_distance_km": _round(sum(distance_present), 1) if distance_present else None,
        "total_calories_kcal": _round(sum(calories_present), 0) if calories_present else None,
        "change": {
            "steps_percentage": steps_change["percentage"],
            "distance_km": distance_change["value"],
            "calories_percentage": calories_change["percentage"],
        },
        "daily": daily,
        "_category_score": trend_score,
        "_steps_direction": steps_change["direction"],
    }


# ---------------------------------------------------------------------------
# Top-level assembly
# ---------------------------------------------------------------------------

def compute_summary(
    device: DeviceRecord,
    sleep_records: list[SleepRecord],
    health_records: list[HealthRecord],
    activity_records: list[ActivityRecord],
    period: dict,
) -> dict:
    period_dates = date_range(period["period_start"], period["period_end"])
    comparison_dates = date_range(period["comparison_start"], period["comparison_end"])

    sleep_by_date = {r.date: r for r in sleep_records}
    health_by_date = {r.date: r for r in health_records}
    activity_by_date = {r.date: r for r in activity_records}

    sleep_summary = _sleep_summary(period_dates, comparison_dates, sleep_by_date)
    health_summary = _health_summary(period_dates, comparison_dates, health_by_date)
    activity_summary = _activity_summary(period_dates, comparison_dates, activity_by_date)

    valid_days = len({
        d for d in period_dates
        if d in sleep_by_date or d in health_by_date or d in activity_by_date
    })

    sleep_score = sleep_summary["_composite_score"]
    health_score = health_summary["_category_score"]
    activity_score = activity_summary["_category_score"]

    weighted = [(sleep_score, 0.4), (health_score, 0.4), (activity_score, 0.2)]
    available = [(score, weight) for score, weight in weighted if score is not None]
    overall_score = None
    if available:
        weight_sum = sum(weight for _, weight in available)
        overall_score = round(sum(score * weight for score, weight in available) / weight_sum)

    sleep_status = _category_status_from_score(sleep_score, sleep_summary["_total_change"]["direction"])
    health_status = _category_status_from_score(health_score, None)
    activity_status = _category_status_from_score(activity_score, activity_summary["_steps_direction"])
    overall_status = _category_status_from_score(overall_score, None)

    # Deterministic, evidence-ranked (not AI-ranked) list of the metrics most worth surfacing:
    # worst status first, then largest adverse magnitude of change.
    candidates = []
    for metric in health_summary["metrics"]:
        if metric["status"] in ("attention", "abnormal"):
            candidates.append({
                "id": f"priority_{metric['key']}",
                "metric": metric["key"],
                "severity": "abnormal" if metric["status"] == "abnormal" else "warning",
                "title": metric["label"],
                "value": metric["value"],
                "unit": metric["unit"],
                "change_value": metric["change_value"],
                "change_percentage": metric["change_percentage"],
                "_rank": 0 if metric["status"] == "abnormal" else 1,
            })
    for metric_row in health_summary["metrics"]:
        if metric_row["key"] == "blood_oxygen":
            present = [v for v in _health_daily_values(period_dates, health_by_date, ("bloodOxygen", "oxygens")) if v is not None]
            low_readings = [(d, v) for d, v in zip(period_dates, _health_daily_values(period_dates, health_by_date, ("bloodOxygen", "oxygens"))) if v is not None and v < _BLOOD_OXYGEN_REFERENCE[0]]
            if low_readings and metric_row["status"] not in ("attention", "abnormal"):
                worst_date, worst_value = min(low_readings, key=lambda item: item[1])
                candidates.append({
                    "id": "priority_blood_oxygen_low_reading",
                    "metric": "blood_oxygen",
                    "severity": "abnormal",
                    "title": "血氧曾出現較低數值",
                    "value": metric_row["value"],
                    "minimum_value": worst_value,
                    "unit": "%",
                    "occurred_at": worst_date,
                    "_rank": 0,
                })
    candidates.sort(key=lambda c: c["_rank"])
    priority_items = []
    for c in candidates[:3]:
        c.pop("_rank", None)
        c.setdefault("occurred_at", None)
        c["action_label"] = "查看健康詳情"
        priority_items.append(c)

    for summary in (sleep_summary, health_summary, activity_summary):
        for internal_key in list(summary.keys()):
            if internal_key.startswith("_"):
                summary.pop(internal_key)

    return {
        "period": {
            "start_date": period["period_start"],
            "end_date": period["period_end"],
            "days": PERIOD_DAYS,
            "label": f"{period['period_start']}–{period['period_end']}",
        },
        "comparison_period": {
            "start_date": period["comparison_start"],
            "end_date": period["comparison_end"],
            "days": PERIOD_DAYS,
        },
        "data_quality": {
            "coverage_percentage": round(valid_days / PERIOD_DAYS * 100),
            "valid_days": valid_days,
            "expected_days": PERIOD_DAYS,
            "last_synced_at": device.last_sync,
            "device_name": device.name,
            "warnings": [] if valid_days == PERIOD_DAYS else ["部分日期沒有同步資料"],
        },
        "overall": {
            "score": overall_score,
            "score_max": 100,
            "status": overall_status,
        },
        "priority_items": priority_items,
        "category_summary": {
            "sleep": {"score": sleep_score, "score_max": 100, "status": sleep_status},
            "health": {"score": health_score, "score_max": 100, "status": health_status},
            "activity": {"score": activity_score, "score_max": 100, "status": activity_status},
        },
        "sleep_summary": sleep_summary,
        "health_summary": health_summary,
        "activity_summary": activity_summary,
    }
