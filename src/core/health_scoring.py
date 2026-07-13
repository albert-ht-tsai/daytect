"""Deterministic 0-100 reference scoring tables for sleep and health metrics.

These tables turn a raw metric value into a 0-100 score using fixed, non-personalized cut
points — the same system-computes-the-number / AI-writes-the-narrative split used elsewhere in
this codebase (see analysis/services/data_summary_service.py's _compute_metric_status). Callers
that want an AI-personalized assessment should pass these scores to the AI as an *initial
reference value* to reason from, not treat them as a final personalized verdict.

Boundary conventions fixed from the original source table (each band below is one specific,
already-resolved band; do not re-derive it from a printed range like "540-600" on your own):
- Total Sleep Time: 420-540 min is the top (100) band; 540 itself belongs there, not to the
  next-lower 80 band, which now starts strictly above 540 (541-600).
- Deep Sleep Ratio: bands use continuous half-open cut points instead of decimal-rounded labels
  (e.g. "8-9.9%" / "10-20%" in the source table), so a raw ratio like 7.95 or 9.97 doesn't fall
  into a gap between two decimal-quantized bands.
- Blood Pressure: the source table mixed an AND condition (top band: systolic AND diastolic both
  in range) with OR conditions (lower bands: either one being in that band is enough), which is
  ambiguous once systolic and diastolic fall in different tiers (e.g. 135/65). Resolved here as
  two independent ladders (systolic, diastolic), each scored separately; the overall score is
  the lower (worse) of the two, which reproduces every row of the original table exactly
  (the AND condition falls out naturally: both ladders must score 100 for the pair to score 100).
"""

# ---------------------------------------------------------------------------
# Sleep metrics
# ---------------------------------------------------------------------------

# Composite sleep score weights (sum to 100%).
SLEEP_WEIGHTS = {
    "totalSleepTime": 0.40,
    "deepSleepRatio": 0.25,
    "wakeCount": 0.20,
    "sleepQuality": 0.15,
}


def score_total_sleep_time(minutes: float | None) -> int | None:
    """minutes: total sleep duration for the day/period, in minutes."""
    if minutes is None:
        return None
    if minutes < 240:
        return 10
    if minutes < 300:
        return 30
    if minutes < 360:
        return 50
    if minutes < 390:
        return 70
    if minutes < 420:
        return 85
    if minutes <= 540:
        return 100
    if minutes <= 600:
        return 80
    return 50


def score_deep_sleep_ratio(ratio_percent: float | None) -> int | None:
    """ratio_percent: deep sleep time as a percentage of total sleep time (0-100), i.e.
    deepSleepTime / allSleepTime * 100 — this function does not compute that ratio itself."""
    if ratio_percent is None:
        return None
    if ratio_percent < 5:
        return 30
    if ratio_percent < 8:
        return 60
    if ratio_percent < 10:
        return 80
    if ratio_percent <= 20:
        return 100
    if ratio_percent <= 25:
        return 90
    if ratio_percent <= 30:
        return 75
    return 55


def score_wake_count(count: float | None) -> int | None:
    if count is None:
        return None
    if count <= 1:
        return 100
    if count == 2:
        return 85
    if count == 3:
        return 70
    if count == 4:
        return 55
    if count == 5:
        return 40
    return 20


def score_sleep_quality(level: float | None) -> int | None:
    """level: a 1 (Very Poor) - 5 (Excellent) categorical sleep-quality grade, per the source
    table. NOTE: this is a different scale than the 0-100-style `sleepQuality` value this
    codebase's SleepRecord/data_summary_service otherwise assumes (see
    data_summary_service._SLEEP_QUALITY_NORMAL_MIN, which treats >=70 as normal on a 0-100
    scale) — a caller wiring this in against real device data must first confirm which scale the
    device actually reports and convert accordingly; do not pass a raw 0-100 value in here."""
    if level is None:
        return None
    if level >= 5:
        return 100
    if level == 4:
        return 85
    if level == 3:
        return 65
    if level == 2:
        return 40
    return 20


def score_sleep_composite(
    total_sleep_minutes: float | None,
    deep_sleep_ratio_percent: float | None,
    wake_count: float | None,
    sleep_quality_level: float | None,
) -> dict:
    """Returns each metric's individual score plus the weighted composite (0-100, rounded to the
    nearest integer). A metric with no data (None) is excluded from both its own score and the
    composite, and the remaining weights are re-normalized so missing data doesn't silently drag
    the composite down."""
    scores = {
        "totalSleepTime": score_total_sleep_time(total_sleep_minutes),
        "deepSleepRatio": score_deep_sleep_ratio(deep_sleep_ratio_percent),
        "wakeCount": score_wake_count(wake_count),
        "sleepQuality": score_sleep_quality(sleep_quality_level),
    }
    available = {k: v for k, v in scores.items() if v is not None}
    composite = None
    if available:
        weight_sum = sum(SLEEP_WEIGHTS[k] for k in available)
        composite = round(sum(v * SLEEP_WEIGHTS[k] for k, v in available.items()) / weight_sum)
    return {"scores": scores, "composite": composite}


# ---------------------------------------------------------------------------
# Health metrics (each scored independently; no composite — see module docstring)
# ---------------------------------------------------------------------------

def score_heart_rate(bpm: float | None) -> int | None:
    if bpm is None:
        return None
    if bpm < 40:
        return 25
    if bpm < 50:
        return 55
    if bpm < 60:
        return 85
    if bpm <= 80:
        return 100
    if bpm <= 90:
        return 85
    if bpm <= 100:
        return 65
    if bpm <= 120:
        return 35
    return 10


def _score_systolic(systolic: float) -> int:
    if systolic < 90:
        return 45
    if systolic <= 119:
        return 100
    if systolic <= 129:
        return 85
    if systolic <= 139:
        return 65
    if systolic <= 159:
        return 40
    return 20


def _score_diastolic(diastolic: float) -> int:
    if diastolic < 60:
        return 45
    if diastolic <= 79:
        return 100
    if diastolic <= 89:
        return 65
    if diastolic <= 99:
        return 40
    return 20


def score_blood_pressure(systolic: float | None, diastolic: float | None) -> int | None:
    """See module docstring: scores systolic and diastolic against independent ladders and
    returns the lower (worse) of the two, which reproduces the source table's mixed AND/OR rows
    exactly (e.g. 90-119/60-79 -> 100 requires both ladders at 100; 135/65 -> min(85, 100) = 85;
    125/82 -> min(85, 65) = 65, matching "SYS130-139 or DIA80-89: 65" via the DIA side)."""
    if systolic is None or diastolic is None:
        return None
    return min(_score_systolic(systolic), _score_diastolic(diastolic))


def score_blood_oxygen(spo2_percent: float | None) -> int | None:
    if spo2_percent is None:
        return None
    if spo2_percent < 90:
        return 15
    if spo2_percent <= 92:
        return 45
    if spo2_percent <= 94:
        return 70
    if spo2_percent <= 96:
        return 90
    return 100


def score_temperature(celsius: float | None) -> int | None:
    if celsius is None:
        return None
    if celsius < 35.0:
        return 15
    if celsius < 35.5:
        return 45
    if celsius < 36.1:
        return 80
    if celsius <= 37.2:
        return 100
    if celsius < 38.0:
        return 70
    if celsius < 39.0:
        return 40
    return 15


def score_hrv(ms: float | None) -> int | None:
    if ms is None:
        return None
    if ms < 10:
        return 20
    if ms < 20:
        return 35
    if ms < 30:
        return 55
    if ms < 45:
        return 75
    if ms < 60:
        return 90
    return 100


def score_stress(value: float | None) -> int | None:
    if value is None:
        return None
    if value <= 25:
        return 100
    if value <= 50:
        return 80
    if value <= 75:
        return 55
    return 25


def score_met(value: float | None) -> int | None:
    if value is None:
        return None
    if value < 1.5:
        return 25
    if value < 3.0:
        return 55
    if value < 6.0:
        return 85
    return 100
