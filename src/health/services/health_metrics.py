"""Rule-based reference thresholds for mapping raw health metrics to a status."""

_STATUS_PENALTY = {
    "good": 0,
    "normal": 0,
    "monitor": 8,
    "low": 8,
    "high": 8,
    "critical": 20,
}

_LEVEL_THRESHOLDS = [
    (90, "excellent"),
    (75, "good"),
    (60, "normal"),
    (45, "monitor"),
    (30, "warning"),
    (0, "critical"),
]


def heart_rate_status(bpm: float | None) -> str | None:
    if bpm is None:
        return None
    if bpm < 40:
        return "critical"
    if bpm < 50:
        return "low"
    if bpm <= 100:
        return "normal"
    if bpm <= 120:
        return "monitor"
    if bpm <= 140:
        return "high"
    return "critical"


def hrv_status(ms: float | None) -> str | None:
    if ms is None:
        return None
    if ms < 20:
        return "low"
    if ms < 30:
        return "monitor"
    if ms < 50:
        return "normal"
    return "good"


def blood_pressure_status(systolic: float | None, diastolic: float | None) -> str | None:
    if systolic is None or diastolic is None:
        return None
    if systolic >= 140 or diastolic >= 90:
        return "critical"
    if systolic >= 130 or diastolic >= 80:
        return "high"
    if systolic < 90 or diastolic < 60:
        return "low"
    return "normal"


def blood_oxygen_status(pct: float | None) -> str | None:
    if pct is None:
        return None
    if pct < 90:
        return "critical"
    if pct < 95:
        return "monitor"
    return "normal"


def body_temperature_status(celsius: float | None) -> str | None:
    if celsius is None:
        return None
    if celsius < 36.0:
        return "low"
    if celsius <= 37.2:
        return "normal"
    if celsius <= 38.0:
        return "monitor"
    if celsius <= 39.0:
        return "high"
    return "critical"


def sleep_status(total_minutes: float | None) -> str | None:
    if total_minutes is None:
        return None
    if total_minutes >= 420:
        return "good"
    if total_minutes >= 360:
        return "normal"
    if total_minutes >= 300:
        return "monitor"
    return "low"


def activity_status(steps: float | None) -> str | None:
    if steps is None:
        return None
    if steps >= 10000:
        return "good"
    if steps >= 5000:
        return "normal"
    if steps >= 2000:
        return "monitor"
    return "low"


def level_from_score(score: int) -> str:
    return next(label for threshold, label in _LEVEL_THRESHOLDS if score >= threshold)


def compute_health_score(statuses: dict[str, str | None]) -> tuple[int, str]:
    penalty = sum(_STATUS_PENALTY.get(status, 0) for status in statuses.values() if status)
    score = max(0, min(100, 100 - penalty))
    return score, level_from_score(score)
