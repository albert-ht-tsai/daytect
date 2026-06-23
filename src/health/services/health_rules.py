"""Rule-based comparators used to classify a metric as improve/stable/decrease.

Reference ranges below are common clinical "normal" ranges for an adult at rest;
they are reference points for nudging a metric towards/away from normal, not a
diagnostic claim.
"""

HEART_RATE_RANGE = (60, 100)
RESPIRATORY_RATE_RANGE = (12, 20)
BODY_TEMPERATURE_RANGE = (36.1, 37.2)
SKIN_TEMPERATURE_RANGE = (33.0, 37.0)
BLOOD_OXYGEN_RANGE = (95, 100)
SYSTOLIC_RANGE = (90, 120)
DIASTOLIC_RANGE = (60, 80)

# A change smaller than this percentage is treated as noise, not a real trend.
VITAL_STABLE_THRESHOLD_PCT = 2.0
VOLUME_STABLE_THRESHOLD_PCT = 5.0


def percent_change(current: float | None, previous: float | None) -> float | None:
    if current is None or previous is None or previous == 0:
        return None
    return round((current - previous) / abs(previous) * 100, 2)


def _range_distance(value: float, low: float, high: float) -> float:
    if value < low:
        return low - value
    if value > high:
        return value - high
    return 0.0


def range_status(
    current: float | None,
    previous: float | None,
    low: float,
    high: float,
    threshold_pct: float = VITAL_STABLE_THRESHOLD_PCT,
) -> str:
    """Closer to the normal [low, high] range is improve; further away is decrease."""
    if current is None or previous is None:
        return "stable"

    cur_dist = _range_distance(current, low, high)
    prev_dist = _range_distance(previous, low, high)
    if cur_dist < prev_dist:
        return "improve"
    if cur_dist > prev_dist:
        return "decrease"

    # Equally (ab)normal vs. the range — fall back to comparing the raw values.
    pct = percent_change(current, previous)
    if pct is None or abs(pct) < threshold_pct:
        return "stable"
    return "improve" if pct < 0 else "decrease"


def higher_is_better_status(
    current: float | None, previous: float | None, threshold_pct: float = VOLUME_STABLE_THRESHOLD_PCT
) -> str:
    if current is None or previous is None:
        return "stable"
    pct = percent_change(current, previous)
    if pct is None:
        if current == previous:
            return "stable"
        return "improve" if current > previous else "decrease"
    if abs(pct) < threshold_pct:
        return "stable"
    return "improve" if pct > 0 else "decrease"


def lower_is_better_status(
    current: float | None, previous: float | None, threshold_pct: float = VOLUME_STABLE_THRESHOLD_PCT
) -> str:
    if current is None or previous is None:
        return "stable"
    pct = percent_change(current, previous)
    if pct is None:
        if current == previous:
            return "stable"
        return "improve" if current < previous else "decrease"
    if abs(pct) < threshold_pct:
        return "stable"
    return "improve" if pct < 0 else "decrease"


def majority_status(statuses: list[str | None]) -> str:
    """Plurality vote across sub-statuses; ties (including no data) resolve to stable."""
    clean = [s for s in statuses if s]
    if not clean:
        return "stable"
    counts = {"improve": clean.count("improve"), "stable": clean.count("stable"), "decrease": clean.count("decrease")}
    top_count = max(counts.values())
    leaders = [status for status, count in counts.items() if count == top_count]
    return leaders[0] if len(leaders) == 1 else "stable"


def heart_rate_status(current: float | None, previous: float | None) -> str:
    return range_status(current, previous, *HEART_RATE_RANGE)


def respiratory_rate_status(current: float | None, previous: float | None) -> str:
    return range_status(current, previous, *RESPIRATORY_RATE_RANGE)


def body_temperature_status(current: float | None, previous: float | None) -> str:
    return range_status(current, previous, *BODY_TEMPERATURE_RANGE)


def skin_temperature_status(current: float | None, previous: float | None) -> str:
    return range_status(current, previous, *SKIN_TEMPERATURE_RANGE)


def blood_oxygen_status(current: float | None, previous: float | None) -> str:
    return range_status(current, previous, *BLOOD_OXYGEN_RANGE)


def blood_pressure_status(
    cur_systolic: float | None,
    cur_diastolic: float | None,
    prev_systolic: float | None,
    prev_diastolic: float | None,
) -> str:
    systolic_status = range_status(cur_systolic, prev_systolic, *SYSTOLIC_RANGE)
    diastolic_status = range_status(cur_diastolic, prev_diastolic, *DIASTOLIC_RANGE)
    return majority_status([systolic_status, diastolic_status])


def cardiac_load_status(current: float | None, previous: float | None) -> str:
    return lower_is_better_status(current, previous)


def activity_status(current: dict, previous: dict) -> str:
    statuses = [
        higher_is_better_status(current.get(key), previous.get(key))
        for key in ("steps", "calories", "distanceKm", "sportValue")
        if current.get(key) is not None and previous.get(key) is not None
    ]
    return majority_status(statuses)


def sleep_status(current: dict, previous: dict) -> str:
    statuses = []
    for key, direction in (
        ("sleepQuality", "higher"),
        ("allSleepTime", "higher"),
        ("deepSleepTime", "higher"),
        ("wakeCount", "lower"),
    ):
        c, p = current.get(key), previous.get(key)
        if c is None or p is None:
            continue
        fn = higher_is_better_status if direction == "higher" else lower_is_better_status
        statuses.append(fn(c, p))
    return majority_status(statuses)
