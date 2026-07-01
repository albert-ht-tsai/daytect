"""Reference-range based scoring helpers.

Ranges are common clinical "normal" ranges for an adult at rest, used as
reference points for a 0-100 daily score, not a diagnostic claim.
"""


def _clamp(value: float) -> float:
    return max(0.0, min(100.0, value))


def range_score(value: float | None, low: float, high: float, spread: float) -> float | None:
    """100 within [low, high], decreasing linearly to 0 once `spread` past the edge."""
    if value is None:
        return None
    if low <= value <= high:
        return 100.0
    dist = low - value if value < low else value - high
    return _clamp(100.0 - (dist / spread) * 100.0)


def higher_is_better_score(value: float | None, target: float) -> float | None:
    if value is None or target <= 0:
        return None
    return _clamp((value / target) * 100.0)


def lower_is_better_score(value: float | None, target_max: float, worst: float) -> float | None:
    if value is None:
        return None
    if value <= target_max:
        return 100.0
    if value >= worst:
        return 0.0
    return _clamp(100.0 * (worst - value) / (worst - target_max))


def weighted_average(components: list[tuple[float | None, float]]) -> float | None:
    """Averages (score, weight) pairs, dropping missing scores and renormalizing weights."""
    valid = [(score, weight) for score, weight in components if score is not None]
    total_weight = sum(weight for _, weight in valid)
    if total_weight == 0:
        return None
    return round(sum(score * weight for score, weight in valid) / total_weight, 1)
