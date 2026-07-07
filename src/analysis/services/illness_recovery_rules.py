"""Deterministic rule engine for the illness/recovery detection feature.

Implements the business rules from the "AI 生病與恢復系統" spec: a single metric deviating
from a user's personal baseline is never sufficient on its own to flag possible illness
(rule 1) — only multiple, persistent, unexplained deviations count (rules 2-4). Recent high
activity or insufficient sleep can explain away part of a deviation (rules 5-6). The
thresholds below are reasonable starting points to make those rules concrete, not clinical
constants (same disclaimer as summary/services/scoring.py).
"""

from typing import Literal

IllnessLevel = Literal["low", "medium", "high", "unknown"]
RecoveryStatus = Literal["recovered", "partially_recovered", "not_recovered", "unknown"]
Trend = Literal["improving", "stable", "worsening", "unknown"]
JointStatus = Literal["NORMAL", "UNDER_RECOVERED", "POSSIBLE_ILLNESS", "POSSIBLE_ILLNESS_RECOVERING", "UNKNOWN"]

MIN_BASELINE_DAYS = 5
PERSISTENCE_DAYS = 2
CO_DEVIATION_HIGH = 3
CO_DEVIATION_MEDIUM = 2

# metric -> (direction that counts as "bad", deviation threshold).
# "up": bad when current is `threshold` above baseline (pct, except body_temperature which is an
# absolute degC delta since its baseline sits near 37 and a pct threshold would be too noisy).
# "down": bad when current is `threshold` below baseline (pct).
METRIC_RULES: dict[str, tuple[Literal["up", "down"], float]] = {
    "resting_hr": ("up", 8.0),
    "body_temperature": ("up", 0.3),
    "hrv": ("down", 15.0),
    "sleep_quality": ("down", 15.0),
    "sleep_duration": ("down", 15.0),
    "activity_steps": ("down", 30.0),
}

# Metrics whose deviation can plausibly be explained away by recent exertion or poor sleep (rule 5/6).
CONFOUNDABLE_METRICS = {"hrv", "resting_hr", "sleep_quality", "sleep_duration"}

METRIC_DISPLAY_NAMES: dict[str, dict[str, str]] = {
    "en": {
        "resting_hr": "resting heart rate",
        "body_temperature": "night body temperature",
        "hrv": "HRV",
        "sleep_quality": "sleep quality",
        "sleep_duration": "sleep duration",
        "activity_steps": "activity level",
    },
    "zh": {
        "resting_hr": "靜息心率",
        "body_temperature": "夜間體溫",
        "hrv": "HRV",
        "sleep_quality": "睡眠品質",
        "sleep_duration": "睡眠時間",
        "activity_steps": "活動量",
    },
}


def deviation_for_metric(metric: str, value: float | None, baseline: float | None) -> dict | None:
    """Returns None when either value is missing, otherwise a dict describing the deviation."""
    if value is None or baseline is None:
        return None
    direction, threshold = METRIC_RULES[metric]
    delta = value - baseline
    pct = (delta / baseline * 100) if baseline else None
    if metric == "body_temperature":
        deviated = delta >= threshold if direction == "up" else delta <= -threshold
    else:
        deviated = pct is not None and (pct >= threshold if direction == "up" else pct <= -threshold)
    return {
        "metric": metric,
        "value": round(value, 2),
        "baseline": round(baseline, 2),
        "delta": round(delta, 2),
        "pct": round(pct, 1) if pct is not None else None,
        "deviated": deviated,
    }


def evaluate_day(date: str, metrics: dict[str, float | None], baseline: dict[str, float | None]) -> dict:
    """Compares one day's metrics against the personal baseline (rule 2: baseline over population norms)."""
    deviations = [
        deviation
        for metric in METRIC_RULES
        if (deviation := deviation_for_metric(metric, metrics.get(metric), baseline.get(metric))) is not None
    ]
    return {
        "date": date,
        "deviations": deviations,
        "count_deviated": sum(1 for d in deviations if d["deviated"]),
    }


def has_confounder(day: dict, high_activity_recent: bool, sleep_insufficient_recent: bool) -> bool:
    """rule 5/6: recent high exertion or insufficient sleep can explain confoundable deviations."""
    deviated_metrics = {d["metric"] for d in day["deviations"] if d["deviated"]}
    if not deviated_metrics & CONFOUNDABLE_METRICS:
        return False
    return high_activity_recent or sleep_insufficient_recent


def classify_illness_level(
    days: list[dict],
    high_activity_recent: bool,
    sleep_insufficient_recent: bool,
    data_sufficient: bool,
) -> IllnessLevel:
    """rule 3/4/5/6/7: multi-metric + persistent + unexplained deviation is what raises the level."""
    if not data_sufficient or not days:
        return "unknown"

    today = days[-1]
    persistent_days = sum(1 for d in days[-PERSISTENCE_DAYS:] if d["count_deviated"] >= CO_DEVIATION_MEDIUM)
    confounded = has_confounder(today, high_activity_recent, sleep_insufficient_recent)

    if today["count_deviated"] >= CO_DEVIATION_HIGH and persistent_days >= PERSISTENCE_DAYS and not confounded:
        return "high"
    if today["count_deviated"] >= CO_DEVIATION_MEDIUM:
        if confounded:
            return "medium" if persistent_days >= PERSISTENCE_DAYS else "low"
        return "medium"
    return "low"


def classify_recovery_status(days: list[dict], data_sufficient: bool) -> RecoveryStatus:
    """rule 8: recovery is a trend judgment (today vs. the prior day), not a single-day snapshot."""
    if not data_sufficient or not days:
        return "unknown"
    today_count = days[-1]["count_deviated"]
    if today_count == 0:
        return "recovered"
    if len(days) < 2:
        return "not_recovered"
    previous_count = days[-2]["count_deviated"]
    return "partially_recovered" if today_count < previous_count else "not_recovered"


def classify_trend(days: list[dict], data_sufficient: bool) -> Trend:
    if not data_sufficient or len(days) < 2:
        return "unknown"
    counts = [d["count_deviated"] for d in days]
    if counts[-1] < counts[0]:
        return "improving"
    if counts[-1] > counts[0]:
        return "worsening"
    return "stable"


def classify_joint_status(illness_level: IllnessLevel, recovery_status: RecoveryStatus) -> JointStatus:
    """Joint interpretation per spec section 10."""
    if illness_level == "unknown" or recovery_status == "unknown":
        return "UNKNOWN"
    if illness_level in ("medium", "high"):
        return "POSSIBLE_ILLNESS_RECOVERING" if recovery_status == "partially_recovered" else "POSSIBLE_ILLNESS"
    return "NORMAL" if recovery_status == "recovered" else "UNDER_RECOVERED"


def build_evidence(today: dict, language: str = "en") -> list[str]:
    """Formats up to 5 deviated metrics as human-readable findings (rule: max 3-5 main findings)."""
    names = METRIC_DISPLAY_NAMES.get(language, METRIC_DISPLAY_NAMES["en"])
    deviated = [d for d in today["deviations"] if d["deviated"]]
    deviated.sort(key=lambda d: abs(d["pct"]) if d["pct"] is not None else abs(d["delta"]), reverse=True)

    lines = []
    for d in deviated[:5]:
        name = names.get(d["metric"], d["metric"])
        is_above = d["delta"] > 0
        magnitude = f"{abs(d['delta'])}°C" if d["metric"] == "body_temperature" else f"{abs(d['pct'])}%"
        if language == "zh":
            lines.append(f"{name}較個人基線{'高於' if is_above else '低於'} {magnitude}")
        else:
            lines.append(f"{name} is {magnitude} {'above' if is_above else 'below'} your personal baseline")
    return lines


def build_alternative_explanation(
    high_activity_recent: bool, sleep_insufficient_recent: bool, language: str = "en"
) -> str | None:
    """rule 5/6: surfaces the confounders considered, so a raised level isn't read as a diagnosis."""
    if not high_activity_recent and not sleep_insufficient_recent:
        return None
    if language == "zh":
        parts = []
        if high_activity_recent:
            parts.append("近期活動負荷偏高")
        if sleep_insufficient_recent:
            parts.append("近期睡眠不足")
        return "、".join(parts) + "，因此部分生理變化也可能與此有關，而非單純疾病所致。"
    parts = []
    if high_activity_recent:
        parts.append("a high activity load")
    if sleep_insufficient_recent:
        parts.append("insufficient sleep")
    return f"Recent {' and '.join(parts)} may also explain part of these changes, not only possible illness."
