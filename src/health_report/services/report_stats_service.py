"""Pure, DB-free statistics layer for health reports: period-date math and turning raw
SleepRecord/HealthRecord/ActivityRecord rows into the fixed-structure numbers the report needs
(averages, day-over-day comparisons, 0-100 scores, deterministic status labels). No AI call and
no DB session here — see health_report_service.py for orchestration and the AI narrative step.

Per the requirement doc: "數值、狀態及比較結果應由後端計算，不應交給 AI 運算" — everything in this
file is deterministic arithmetic over already-uploaded per-day averages (device data is uploaded
as one averaged value per day, not raw per-sample readings — see HealthAvgRecordPayload), never an
AI call.

This module also applies the formulas from `docs/CALCULATION_SPEC.md` (health-score weights,
weekly-change thresholds, key-metric priority ranking, data-completeness gating). See that doc
for the full formula reference and for which parts of the source spec are simplified or not
implemented because this codebase only stores one pre-averaged value per metric per day (no
raw per-sample data, no per-user timezone — the source spec's timezone design is deprecated and
not used here).
"""

import math
import statistics
from datetime import date, datetime, timedelta, timezone

from src.core import health_scoring
from src.device.models.activity_model import ActivityRecord
from src.device.models.device_model import DeviceRecord
from src.device.models.health_model import HealthRecord
from src.device.models.sleep_model import SleepRecord

PERIOD_DAYS = 7

# No per-user/per-device timezone is stored anywhere in this codebase — matches the same fixed
# +08:00 convention used elsewhere (see assistant/services/question_summary_service.py's
# REPORT_TZ). Not configurable per request; the source spec's per-user IANA-timezone design is
# deprecated, so this module has no zoneinfo/tzdata dependency.
REPORT_TZ = timezone(timedelta(hours=8))

# Universally-cited clinical reference ranges (not this codebase's own invention, unlike the
# finer-grained scoring bands in health_scoring.py) — kept to just the two metrics where a single
# widely-agreed "normal range" exists, per the plan's decision not to fabricate bands for metrics
# (stress, HRV, MET, respiratory rate) that don't have one universally-agreed pair of numbers.
_HEART_RATE_REFERENCE = (60, 100)
_BLOOD_OXYGEN_REFERENCE = (95, 100)

# Trailing window used for the body-temperature personal baseline (calculation spec §5: "近
# 14–30 天同時段中位數"). Fixed at the upper end of that range so the baseline has as much signal
# as possible.
TEMPERATURE_BASELINE_DAYS = 30

# Metric-level "significant change" thresholds (calculation spec §3.2). A change is significant
# when it crosses the absolute threshold OR the percent threshold (whichever is set) — either
# condition is sufficient, matching the source doc's "或" wording.
_WEEKLY_CHANGE_THRESHOLDS = {
    "sleep_total_minutes": {"absolute": 30, "percent": 8, "label": "睡眠時間", "unit": "分鐘"},
    "deep_sleep_ratio": {"absolute": 5, "percent": None, "label": "深睡比例", "unit": "%"},
    "sleep_interruptions": {"absolute": 2, "percent": 20, "label": "睡眠中斷次數", "unit": "次"},
    "resting_heart_rate": {"absolute": 5, "percent": 8, "label": "靜息心率", "unit": "bpm"},
    "hrv": {"absolute": None, "percent": 10, "label": "HRV", "unit": "ms"},
    "blood_pressure_systolic": {"absolute": 5, "percent": None, "label": "收縮壓", "unit": "mmHg"},
    "blood_pressure_diastolic": {"absolute": 5, "percent": None, "label": "舒張壓", "unit": "mmHg"},
    "blood_oxygen": {"absolute": 2, "percent": None, "label": "血氧", "unit": "%"},
    "steps": {"absolute": None, "percent": 15, "label": "步數", "unit": "steps"},
}

# Which trend direction ("up" or "down") is the favorable one for a metric — used to derive
# `health_impact` for weekly_changes entries. Blood pressure is handled separately (judged by
# score, i.e. "依目標區間判定" per the spec, not by raw direction).
_FAVORABLE_TREND = {
    "sleep_total_minutes": "up",
    "deep_sleep_ratio": "up",
    "sleep_interruptions": "down",
    "resting_heart_rate": "down",
    "hrv": "up",
    "blood_oxygen": "up",
    "steps": "up",
}


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


def baseline_date_range(period_start: str, days: int = TEMPERATURE_BASELINE_DAYS) -> list[str]:
    """The trailing window ending the day before `period_start`, used for the body-temperature
    personal baseline (calculation spec §5)."""
    start_d = date.fromisoformat(period_start)
    end_d = start_d - timedelta(days=1)
    begin_d = end_d - timedelta(days=days - 1)
    return date_range(begin_d.isoformat(), end_d.isoformat())


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
    favorable/unfavorable read must interpret `direction` themselves per metric.

    Per calculation spec §1: previous missing or zero -> percentage is null (comparison_status
    "insufficient_data" is the caller's responsibility to attach, since not every caller of this
    helper produces a weekly_changes-shaped entry)."""
    if current is None or previous is None:
        return {"value": None, "percentage": None, "direction": "stable"}
    value = current - previous
    percentage = None if previous == 0 else round(value / previous * 100, 1)
    direction = "stable" if abs(value) < 1e-9 else ("up" if value > 0 else "down")
    return {"value": _round(value, 2), "percentage": percentage, "direction": direction}


def _completion_rate(values: list[float | None]) -> float:
    """valid_samples / expected_samples * 100 (calculation spec §1)."""
    if not values:
        return 0.0
    present = sum(1 for v in values if v is not None)
    return round(present / len(values) * 100, 1)


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


def _is_significant_change(metric_key: str, absolute_change: float | None, percent_change: float | None) -> bool:
    threshold = _WEEKLY_CHANGE_THRESHOLDS.get(metric_key, {})
    if absolute_change is None:
        return False
    abs_thr = threshold.get("absolute")
    pct_thr = threshold.get("percent")
    if abs_thr is not None and abs(absolute_change) >= abs_thr:
        return True
    if pct_thr is not None and percent_change is not None and abs(percent_change) >= pct_thr:
        return True
    return False


def _weekly_change_severity(score: int | None, health_impact: str) -> str:
    if score is not None:
        if score < 60:
            return "critical"
        if score < 85:
            return "warning"
        return "info"
    return "warning" if health_impact == "negative" else "info"


def _health_impact(metric_key: str, trend: str, score: int | None = None, comparison_score: int | None = None) -> str:
    if metric_key in ("blood_pressure_systolic", "blood_pressure_diastolic"):
        if score is None or comparison_score is None:
            return "depends"
        if score > comparison_score:
            return "positive"
        if score < comparison_score:
            return "negative"
        return "neutral"
    if trend == "stable":
        return "neutral"
    favorable = _FAVORABLE_TREND.get(metric_key)
    if favorable is None:
        return "depends"
    return "positive" if trend == favorable else "negative"


def _weekly_change_entry(metric_key: str, current: float | None, previous: float | None,
                          current_completion: float, previous_completion: float,
                          score: int | None = None, comparison_score: int | None = None) -> dict | None:
    """Builds one calculation-spec §3.2 `weekly_changes` entry, or None if the metric isn't
    present or its change doesn't cross the significance threshold for that metric."""
    if current is None:
        return None
    threshold = _WEEKLY_CHANGE_THRESHOLDS.get(metric_key, {})
    change = _change(current, previous)
    if previous is None:
        return None  # "insufficient_data" comparisons aren't surfaced as a weekly change event
    if not _is_significant_change(metric_key, change["value"], change["percentage"]):
        return None
    label = threshold.get("label", metric_key)
    unit = threshold.get("unit", "")
    impact = _health_impact(metric_key, change["direction"], score, comparison_score)
    severity = _weekly_change_severity(score, impact)
    verb = {"up": "上升", "down": "下降", "stable": "持平"}[change["direction"]]
    message = f"{label}較前期{verb}" + (f" {abs(change['value'])}{unit}" if change["value"] is not None else "")
    return {
        "metric": metric_key,
        "current": current,
        "previous": previous,
        "absolute_change": change["value"],
        "change_percent": change["percentage"],
        "trend": change["direction"],
        "health_impact": impact,
        "severity": severity,
        "message": message,
        "data_quality": {
            "current_completion": current_completion,
            "previous_completion": previous_completion,
        },
    }


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


def _parse_iso_datetime(iso_str: str | None) -> datetime | None:
    if not iso_str:
        return None
    try:
        return datetime.fromisoformat(iso_str)
    except ValueError:
        return None


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
    """Per calculation spec §4: time_in_bed/sleep_efficiency/awake_duration derived from the
    actual sleep_down -> sleep_up timestamps (not the circular clock-time-of-day used for
    regularity), and a day is flagged `invalid` when time_in_bed <= 0, total sleep exceeds 18h, or
    the sleep-stage minutes add up to materially more than time_in_bed."""
    daily = []
    for d in dates:
        record = by_date.get(d)
        summary = (record.sleep_summary or {}) if record else {}
        total = summary.get("allSleepTime")
        deep = summary.get("deepSleepTime")
        light = summary.get("lowSleepTime")
        rem = summary.get("remSleepTime")
        sleep_down = summary.get("sleepDown")
        sleep_up = summary.get("sleepUp")

        down_dt = _parse_iso_datetime(sleep_down)
        up_dt = _parse_iso_datetime(sleep_up)
        time_in_bed = (up_dt - down_dt).total_seconds() / 60 if down_dt and up_dt else None

        sleep_efficiency = None
        if total is not None and time_in_bed and time_in_bed > 0:
            sleep_efficiency = total / time_in_bed * 100

        awake_duration = None
        if total is not None and time_in_bed is not None:
            awake_duration = max(time_in_bed - total, 0)

        stage_values = [v for v in (deep, light, rem) if v is not None]
        stage_sum = sum(stage_values) if stage_values else None

        invalid = False
        if time_in_bed is not None and time_in_bed <= 0:
            invalid = True
        if total is not None and total > 18 * 60:
            invalid = True
        if time_in_bed is not None and time_in_bed > 0 and stage_sum is not None and stage_sum > time_in_bed * 1.05:
            invalid = True

        daily.append({
            "date": d,
            "total_sleep_minutes": total,
            "deep_sleep_minutes": deep,
            "light_sleep_minutes": light,
            "rem_sleep_minutes": rem,
            "wake_count": summary.get("wakeCount"),
            "sleep_down": sleep_down,
            "sleep_up": sleep_up,
            "score": summary.get("sleepQuality"),
            "time_in_bed_minutes": _round(time_in_bed, 0),
            "sleep_efficiency": _round(sleep_efficiency, 1),
            "awake_duration_minutes": _round(awake_duration, 0),
            "invalid": invalid,
        })
    return daily


def _sleep_summary(period_dates: list[str], comparison_dates: list[str], by_date: dict[str, SleepRecord]) -> dict:
    daily = _sleep_daily(period_dates, by_date)
    comparison_daily = _sleep_daily(comparison_dates, by_date)

    def col(rows: list[dict], key: str) -> list[float | None]:
        # Invalid days (calculation spec §4) are excluded from every weekly average, not just
        # displayed with a caveat, since a >18h/negative-duration record is a device-side error.
        return [row[key] for row in rows if not row["invalid"]]

    avg_total = _avg(col(daily, "total_sleep_minutes"))
    avg_deep = _avg(col(daily, "deep_sleep_minutes"))
    avg_light = _avg(col(daily, "light_sleep_minutes"))
    avg_rem = _avg(col(daily, "rem_sleep_minutes"))
    avg_wake_count = _avg(col(daily, "wake_count"))
    avg_quality = _avg(col(daily, "score"))
    avg_time_in_bed = _avg(col(daily, "time_in_bed_minutes"))
    avg_efficiency = _avg(col(daily, "sleep_efficiency"))
    avg_awake = _avg(col(daily, "awake_duration_minutes"))

    comparison_avg_total = _avg(col(comparison_daily, "total_sleep_minutes"))
    comparison_avg_deep = _avg(col(comparison_daily, "deep_sleep_minutes"))
    comparison_avg_rem = _avg(col(comparison_daily, "rem_sleep_minutes"))
    comparison_avg_wake_count = _avg(col(comparison_daily, "wake_count"))

    bedtime_minutes = [_time_to_minutes(row["sleep_down"]) for row in daily if not row["invalid"]]
    wake_minutes = [_time_to_minutes(row["sleep_up"]) for row in daily if not row["invalid"]]

    deep_ratio = None if not avg_total else (avg_deep or 0) / avg_total * 100
    rem_ratio = None if not avg_total else (avg_rem or 0) / avg_total * 100
    comparison_deep_ratio = None if not comparison_avg_total else (comparison_avg_deep or 0) / comparison_avg_total * 100

    composite = health_scoring.score_sleep_composite(
        total_sleep_minutes=avg_total,
        deep_sleep_ratio_percent=deep_ratio,
        wake_count=avg_wake_count,
        # sleepQuality is on a different 0-100 device scale than the 1-5 grade this scorer
        # expects (see health_scoring.score_sleep_quality's docstring) — excluded, not converted.
        sleep_quality_level=None,
    )

    def completion_col(rows: list[dict], key: str) -> list[float | None]:
        # Unlike col(), keeps one slot per expected day (invalid days count as missing rather
        # than being dropped from the denominator) so completion_rate is always valid_samples /
        # expected_samples over the full period, per calculation spec §1.
        return [row[key] if not row["invalid"] else None for row in rows]

    completion_rate = _completion_rate(completion_col(daily, "total_sleep_minutes"))

    weekly_change_inputs = [
        {
            "metric": "sleep_total_minutes",
            "current": avg_total,
            "previous": comparison_avg_total,
            "current_completion": completion_rate,
            "previous_completion": _completion_rate(completion_col(comparison_daily, "total_sleep_minutes")),
            "score": health_scoring.score_total_sleep_time(avg_total),
        },
        {
            "metric": "deep_sleep_ratio",
            "current": _round(deep_ratio, 1),
            "previous": _round(comparison_deep_ratio, 1),
            "current_completion": completion_rate,
            "previous_completion": _completion_rate(completion_col(comparison_daily, "deep_sleep_minutes")),
            "score": health_scoring.score_deep_sleep_ratio(deep_ratio),
        },
        {
            "metric": "sleep_interruptions",
            "current": _round(avg_wake_count, 1),
            "previous": _round(comparison_avg_wake_count, 1),
            "current_completion": completion_rate,
            "previous_completion": _completion_rate(completion_col(comparison_daily, "wake_count")),
            "score": health_scoring.score_wake_count(avg_wake_count),
        },
    ]

    return {
        "average_total_sleep_minutes": _round(avg_total, 0),
        "average_deep_sleep_minutes": _round(avg_deep, 0),
        "average_light_sleep_minutes": _round(avg_light, 0),
        "average_rem_sleep_minutes": _round(avg_rem, 0),
        "average_wake_count": _round(avg_wake_count, 1),
        "average_bedtime": _minutes_to_hhmm(_circular_mean_minutes(bedtime_minutes)),
        "average_wake_time": _minutes_to_hhmm(_circular_mean_minutes(wake_minutes)),
        "sleep_regularity_score": _circular_regularity_score(bedtime_minutes),
        "average_time_in_bed_minutes": _round(avg_time_in_bed, 0),
        "average_sleep_efficiency": _round(avg_efficiency, 1),
        "average_awake_duration_minutes": _round(avg_awake, 0),
        "deep_sleep_ratio_percent": _round(deep_ratio, 1),
        "rem_sleep_ratio_percent": _round(rem_ratio, 1),
        "completion_rate": completion_rate,
        "invalid_days_excluded": sum(1 for row in daily if row["invalid"]),
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
        "_weekly_change_inputs": weekly_change_inputs,
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

# Maps a health_summary metric `key` onto its calculation-spec §3.2 weekly-change threshold key,
# where one exists (body_temperature/stress/met/respiratory_rate have no threshold row in the
# source doc, so they don't produce weekly_changes entries).
_HEALTH_WEEKLY_CHANGE_KEY = {
    "heart_rate": "resting_heart_rate",
    "hrv": "hrv",
    "blood_oxygen": "blood_oxygen",
}


def _health_daily_values(dates: list[str], by_date: dict[str, HealthRecord], path: tuple) -> list[float | None]:
    return [_get(by_date[d].data, *path) if d in by_date else None for d in dates]


def _health_summary(
    period_dates: list[str],
    comparison_dates: list[str],
    by_date: dict[str, HealthRecord],
    baseline_temperatures: list[float] | None = None,
) -> dict:
    metrics = []
    scores_for_category: list[int] = []
    weekly_change_inputs = []

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
        completion_rate = _completion_rate(values)

        # persistence_score (calculation spec §3.3): share of this metric's valid days in the
        # period that individually scored "abnormal" (<60), i.e. how sustained the issue was
        # rather than a one-off reading.
        persistence_score = None
        if scorer and present:
            daily_scores = [scorer(v) for v in values if v is not None]
            abnormal_days = sum(1 for s in daily_scores if s is not None and s < 60)
            persistence_score = round(abnormal_days / len(daily_scores) * 100, 1)

        entry = {
            "key": key,
            "label": label,
            "value": _round(avg, 1),
            "unit": unit,
            "status": _metric_status_from_score(score) if scorer else (
                "insufficient_data" if avg is None else "normal"
            ),
            "score": score,
            "change_value": change["value"],
            "change_percentage": change["percentage"],
            "change_direction": change["direction"],
            "completion_rate": completion_rate,
            "persistence_score": persistence_score,
        }
        if present:
            entry["minimum"] = _round(min(present), 1)
            entry["maximum"] = _round(max(present), 1)
        if key == "heart_rate":
            entry["reference_min"], entry["reference_max"] = _HEART_RATE_REFERENCE
        if key == "blood_oxygen":
            entry["reference_min"], entry["reference_max"] = _BLOOD_OXYGEN_REFERENCE
            # Day-count stand-in for the source spec's per-sample "<95%/<90% reading duration"
            # (calculation spec §5 note) — this codebase only has one averaged value per day.
            entry["days_below_95"] = sum(1 for v in values if v is not None and v < 95)
            entry["days_below_90"] = sum(1 for v in values if v is not None and v < 90)
        if key == "stress":
            # Day-count stand-in for "cumulative minutes >= 70" (no per-minute stress samples).
            entry["high_stress_days"] = sum(1 for v in values if v is not None and v >= 70)
        if key == "body_temperature" and baseline_temperatures:
            baseline_present = [v for v in baseline_temperatures if v is not None]
            if baseline_present:
                baseline_median = statistics.median(baseline_present)
                entry["baseline_median"] = _round(baseline_median, 1)
                entry["baseline_delta"] = _round(avg - baseline_median, 1) if avg is not None else None
        metrics.append(entry)

        change_key = _HEALTH_WEEKLY_CHANGE_KEY.get(key)
        if change_key:
            weekly_change_inputs.append({
                "metric": change_key,
                "current": entry["value"],
                "previous": _round(comparison_avg, 1),
                "current_completion": completion_rate,
                "previous_completion": _completion_rate(comparison_values),
                "score": score,
            })

    # Blood pressure: two-valued metric, handled separately from the table above.
    systolic_values = _health_daily_values(period_dates, by_date, ("bloodPressure", "systolic"))
    diastolic_values = _health_daily_values(period_dates, by_date, ("bloodPressure", "diastolic"))
    comparison_systolic = _health_daily_values(comparison_dates, by_date, ("bloodPressure", "systolic"))
    comparison_diastolic = _health_daily_values(comparison_dates, by_date, ("bloodPressure", "diastolic"))
    avg_systolic, avg_diastolic = _avg(systolic_values), _avg(diastolic_values)
    comparison_avg_systolic, comparison_avg_diastolic = _avg(comparison_systolic), _avg(comparison_diastolic)
    bp_score = health_scoring.score_blood_pressure(avg_systolic, avg_diastolic)
    comparison_bp_score = health_scoring.score_blood_pressure(comparison_avg_systolic, comparison_avg_diastolic)
    if bp_score is not None:
        scores_for_category.append(bp_score)
    systolic_change = _change(avg_systolic, comparison_avg_systolic)
    diastolic_change = _change(avg_diastolic, comparison_avg_diastolic)
    bp_completion = _completion_rate(systolic_values)
    bp_persistence = None
    if systolic_values and diastolic_values:
        daily_bp_scores = [
            health_scoring.score_blood_pressure(s, d)
            for s, d in zip(systolic_values, diastolic_values)
            if s is not None and d is not None
        ]
        if daily_bp_scores:
            abnormal_days = sum(1 for s in daily_bp_scores if s is not None and s < 60)
            bp_persistence = round(abnormal_days / len(daily_bp_scores) * 100, 1)
    metrics.insert(1, {
        "key": "blood_pressure",
        "label": "平均血壓",
        "value": {"systolic": _round(avg_systolic, 0), "diastolic": _round(avg_diastolic, 0)},
        "unit": "mmHg",
        "status": _metric_status_from_score(bp_score),
        "score": bp_score,
        "change_value": {"systolic": systolic_change["value"], "diastolic": diastolic_change["value"]},
        "change_percentage": None,
        "change_direction": systolic_change["direction"],
        "completion_rate": bp_completion,
        "persistence_score": bp_persistence,
    })

    weekly_change_inputs.append({
        "metric": "blood_pressure_systolic",
        "current": _round(avg_systolic, 0),
        "previous": _round(comparison_avg_systolic, 0),
        "current_completion": bp_completion,
        "previous_completion": _completion_rate(comparison_systolic),
        "score": bp_score,
        "comparison_score": comparison_bp_score,
    })
    weekly_change_inputs.append({
        "metric": "blood_pressure_diastolic",
        "current": _round(avg_diastolic, 0),
        "previous": _round(comparison_avg_diastolic, 0),
        "current_completion": _completion_rate(diastolic_values),
        "previous_completion": _completion_rate(comparison_diastolic),
        "score": bp_score,
        "comparison_score": comparison_bp_score,
    })

    category_score = round(sum(scores_for_category) / len(scores_for_category)) if scores_for_category else None
    return {
        "metrics": metrics,
        "_category_score": category_score,
        "_weekly_change_inputs": weekly_change_inputs,
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

    completion_rate = _completion_rate(col(daily, "steps"))

    # Note (calculation spec §6): goal_achievement_rate / active_minutes / MET-minutes from the
    # source doc are NOT implemented — this device payload has no per-user step goal and no
    # per-minute activity-intensity data, only one steps/distance/calories average per day.

    return {
        "average_steps": _round(avg_steps, 0),
        "average_distance_km": _round(avg_distance, 1),
        "average_calories_kcal": _round(avg_calories, 0),
        "total_steps": _round(sum(steps_present), 0) if steps_present else None,
        "total_distance_km": _round(sum(distance_present), 1) if distance_present else None,
        "total_calories_kcal": _round(sum(calories_present), 0) if calories_present else None,
        "completion_rate": completion_rate,
        "change": {
            "steps_percentage": steps_change["percentage"],
            "distance_km": distance_change["value"],
            "calories_percentage": calories_change["percentage"],
        },
        "daily": daily,
        "_category_score": trend_score,
        "_steps_direction": steps_change["direction"],
        "_weekly_change_inputs": [{
            "metric": "steps",
            "current": _round(avg_steps, 0),
            "previous": _round(comparison_avg_steps, 0),
            "current_completion": completion_rate,
            "previous_completion": _completion_rate(col(comparison_daily, "steps")),
            "score": None,
        }],
    }


# ---------------------------------------------------------------------------
# Top-level assembly
# ---------------------------------------------------------------------------

# Category weights per calculation spec §3.1 (sleep 30% / health 40% / activity 20%). The
# remaining 10% is reserved for a frontend-appended medication component that this backend never
# computes (see spec doc note on schema_version) — omitting it here and renormalizing over
# whichever of these three categories has data reproduces the doc's "重新正規化" rule exactly.
_CATEGORY_WEIGHTS = {"sleep": 0.30, "health": 0.40, "activity": 0.20}

# Minimum valid days (in both the period and the comparison period) required before weekly
# comparisons are produced at all (calculation spec §1: "本週或前週有效日少於 3 天時，不輸出週比較").
_MIN_VALID_DAYS_FOR_COMPARISON = 3

# A metric with a per-day completion rate below this is excluded from key-metric ranking
# (calculation spec §1: "單一指標完整率低於 50% 時，不進入關鍵指標排序").
_MIN_COMPLETION_FOR_RANKING = 50


def _priority_score(abnormal_score: float, change_score: float, persistence_score: float | None, data_confidence: float) -> float:
    return (
        abnormal_score * 0.40
        + change_score * 0.25
        + (persistence_score or 0) * 0.20
        + data_confidence * 0.15
    )


def _change_score(change_percentage: float | None, change_value: float | None, pct_threshold: float | None, abs_threshold: float | None) -> float:
    if pct_threshold and change_percentage is not None:
        return min(100.0, abs(change_percentage) / pct_threshold * 100)
    if abs_threshold and change_value is not None:
        return min(100.0, abs(change_value) / abs_threshold * 100)
    return 0.0


def compute_summary(
    device: DeviceRecord,
    sleep_records: list[SleepRecord],
    health_records: list[HealthRecord],
    activity_records: list[ActivityRecord],
    period: dict,
    baseline_health_records: list[HealthRecord] | None = None,
) -> dict:
    period_dates = date_range(period["period_start"], period["period_end"])
    comparison_dates = date_range(period["comparison_start"], period["comparison_end"])

    sleep_by_date = {r.date: r for r in sleep_records}
    health_by_date = {r.date: r for r in health_records}
    activity_by_date = {r.date: r for r in activity_records}

    baseline_temperatures = [
        _get(r.data, "bodyTemperature", "temperature") for r in (baseline_health_records or [])
    ]

    sleep_summary = _sleep_summary(period_dates, comparison_dates, sleep_by_date)
    health_summary = _health_summary(period_dates, comparison_dates, health_by_date, baseline_temperatures)
    activity_summary = _activity_summary(period_dates, comparison_dates, activity_by_date)

    valid_days = len({
        d for d in period_dates
        if d in sleep_by_date or d in health_by_date or d in activity_by_date
    })
    comparison_valid_days = len({
        d for d in comparison_dates
        if d in sleep_by_date or d in health_by_date or d in activity_by_date
    })

    sleep_score = sleep_summary["_composite_score"]
    health_score = health_summary["_category_score"]
    activity_score = activity_summary["_category_score"]

    weighted = [(sleep_score, _CATEGORY_WEIGHTS["sleep"]), (health_score, _CATEGORY_WEIGHTS["health"]), (activity_score, _CATEGORY_WEIGHTS["activity"])]
    available = [(score, weight) for score, weight in weighted if score is not None]
    overall_score = None
    if available:
        weight_sum = sum(weight for _, weight in available)
        overall_score = round(sum(score * weight for score, weight in available) / weight_sum)

    sleep_status = _category_status_from_score(sleep_score, sleep_summary["_total_change"]["direction"])
    health_status = _category_status_from_score(health_score, None)
    activity_status = _category_status_from_score(activity_score, activity_summary["_steps_direction"])
    overall_status = _category_status_from_score(overall_score, None)

    category_statuses = {"sleep": sleep_status, "health": health_status, "activity": activity_status}
    reason_codes = [
        f"{category.upper()}_{status.upper()}"
        for category, status in category_statuses.items()
        if status in ("attention", "abnormal", "insufficient_data")
    ]

    data_completeness = {
        "sleep": round(len({d for d in period_dates if d in sleep_by_date}) / PERIOD_DAYS * 100),
        "health": round(len({d for d in period_dates if d in health_by_date}) / PERIOD_DAYS * 100),
        "activity": round(len({d for d in period_dates if d in activity_by_date}) / PERIOD_DAYS * 100),
    }

    # --- weekly_changes (calculation spec §3.2) -----------------------------------------------
    comparison_allowed = valid_days >= _MIN_VALID_DAYS_FOR_COMPARISON and comparison_valid_days >= _MIN_VALID_DAYS_FOR_COMPARISON
    weekly_changes = []
    if comparison_allowed:
        all_inputs = (
            sleep_summary["_weekly_change_inputs"]
            + health_summary["_weekly_change_inputs"]
            + activity_summary["_weekly_change_inputs"]
        )
        for item in all_inputs:
            entry = _weekly_change_entry(
                item["metric"], item["current"], item["previous"],
                item["current_completion"], item["previous_completion"],
                score=item.get("score"), comparison_score=item.get("comparison_score"),
            )
            if entry:
                weekly_changes.append(entry)

    # --- key metrics / priority_items (calculation spec §3.3) --------------------------------
    candidates = []
    for metric in health_summary["metrics"]:
        if metric["status"] not in ("attention", "abnormal"):
            continue
        if metric["completion_rate"] < _MIN_COMPLETION_FOR_RANKING:
            continue
        if metric["key"] == "blood_pressure":
            threshold = _WEEKLY_CHANGE_THRESHOLDS["blood_pressure_systolic"]
            change_val = metric["change_value"] or {}
            change_score = max(
                _change_score(None, change_val.get("systolic"), None, threshold["absolute"]),
                _change_score(None, change_val.get("diastolic"), None, threshold["absolute"]),
            )
        else:
            change_key = _HEALTH_WEEKLY_CHANGE_KEY.get(metric["key"])
            threshold = _WEEKLY_CHANGE_THRESHOLDS.get(change_key, {})
            change_score = _change_score(metric["change_percentage"], metric["change_value"], threshold.get("percent"), threshold.get("absolute"))
        abnormal_score = 100 - metric["score"] if metric["score"] is not None else 100
        candidates.append({
            "id": f"priority_{metric['key']}",
            "metric": metric["key"],
            "severity": "abnormal" if metric["status"] == "abnormal" else "warning",
            "title": metric["label"],
            "value": metric["value"],
            "unit": metric["unit"],
            "change_value": metric["change_value"],
            "change_percentage": metric["change_percentage"],
            "_priority_score": _priority_score(
                abnormal_score=abnormal_score,
                change_score=change_score,
                persistence_score=metric["persistence_score"],
                data_confidence=metric["completion_rate"],
            ),
        })
    for metric_row in health_summary["metrics"]:
        if metric_row["key"] == "blood_oxygen":
            present = [v for v in _health_daily_values(period_dates, health_by_date, ("bloodOxygen", "oxygens")) if v is not None]
            low_readings = [(d, v) for d, v in zip(period_dates, _health_daily_values(period_dates, health_by_date, ("bloodOxygen", "oxygens"))) if v is not None and v < _BLOOD_OXYGEN_REFERENCE[0]]
            if low_readings and metric_row["status"] not in ("attention", "abnormal") and metric_row["completion_rate"] >= _MIN_COMPLETION_FOR_RANKING:
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
                    "_priority_score": _priority_score(
                        abnormal_score=100,
                        change_score=0,
                        persistence_score=round(len(low_readings) / max(len(present), 1) * 100, 1),
                        data_confidence=metric_row["completion_rate"],
                    ),
                })
    candidates.sort(key=lambda c: c["_priority_score"], reverse=True)
    priority_items = []
    for c in candidates[:5]:
        c.pop("_priority_score", None)
        c.setdefault("occurred_at", None)
        c["action_label"] = "查看健康詳情"
        priority_items.append(c)

    for summary in (sleep_summary, health_summary, activity_summary):
        for internal_key in list(summary.keys()):
            if internal_key.startswith("_"):
                summary.pop(internal_key)

    data_quality_warnings = [] if valid_days == PERIOD_DAYS else ["部分日期沒有同步資料"]
    if not comparison_allowed:
        data_quality_warnings.append("本期或前期有效資料天數不足（需至少 3 天），不提供週比較")

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
            "comparison_valid_days": comparison_valid_days,
            "expected_days": PERIOD_DAYS,
            "last_synced_at": device.last_sync,
            "device_name": device.name,
            "warnings": data_quality_warnings,
        },
        "overall": {
            "score": overall_score,
            "score_max": 100,
            "status": overall_status,
            "reason_codes": reason_codes,
            "data_completeness": data_completeness,
        },
        "weekly_changes": weekly_changes,
        "priority_items": priority_items,
        "category_summary": {
            "sleep": {"score": sleep_score, "score_max": 100, "status": sleep_status},
            "health": {"score": health_score, "score_max": 100, "status": health_status},
            "activity": {"score": activity_score, "score_max": 100, "status": activity_status},
        },
        "sleep_summary": sleep_summary,
        "health_summary": health_summary,
        "activity_summary": activity_summary,
        "_comparison_allowed": comparison_allowed,
    }
