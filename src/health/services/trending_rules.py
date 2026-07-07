"""Deterministic rule engine for the health-trending feature.

Turns a period's sampled overall-health scores (see summary/services/scoring.py for how a
single day's overall score is computed) into a score_label, and turns the two weakest
scoring categories (sleep/activity/health) into concrete suggestions with an estimated
improvement percentage. Thresholds below are reasonable starting points for a 0-100
composite score, not clinical constants (same disclaimer as scoring.py).
"""

from typing import Literal

ScoreLabel = Literal["Good", "Normal", "Recovering", "Mild Discomfort", "Sick", "Strong Attention"]
Category = Literal["sleep", "activity", "health"]

# score_label sampling thresholds: classification samples just the latest score and the
# trend (latest - first) of the period's score series.
_STRONG_ATTENTION_DROP = -15.0
_STRONG_ATTENTION_SCORE = 40.0
_SICK_SCORE = 55.0
_SICK_DROP = -8.0
_MILD_DISCOMFORT_SCORE = 70.0
_MILD_DISCOMFORT_DRIFT = 3.0
_RECOVERING_RISE = 8.0
_RECOVERING_CEILING = 90.0
_GOOD_SCORE = 85.0
_GOOD_DRIFT = -3.0


def classify_score_label(scores: list[float]) -> ScoreLabel:
    """Samples the latest score and the trend (latest - first) from the period's score
    series to classify overall status. Order matters: sharp drops / very low scores are
    checked first regardless of trend, then a strong upward trend that hasn't yet reached
    a sustained high level is called out as still "Recovering" rather than "Good" —
    otherwise a single recent jump above the "Good" cutoff would immediately read as fully
    recovered even though most of the period was still low."""
    if not scores:
        return "Normal"
    latest = scores[-1]
    trend = latest - scores[0]

    if trend <= _STRONG_ATTENTION_DROP or latest < _STRONG_ATTENTION_SCORE:
        return "Strong Attention"
    if latest < _SICK_SCORE or trend <= _SICK_DROP:
        return "Sick"
    if latest < _MILD_DISCOMFORT_SCORE and trend <= _MILD_DISCOMFORT_DRIFT:
        return "Mild Discomfort"
    if trend >= _RECOVERING_RISE and latest < _RECOVERING_CEILING:
        return "Recovering"
    if latest >= _GOOD_SCORE and trend >= _GOOD_DRIFT:
        return "Good"
    return "Normal"


# category -> (tip when badly low, tip when moderately low)
_SUGGESTIONS: dict[Category, tuple[str, str]] = {
    "sleep": (
        "Maintain a consistent bedtime to keep your circadian rhythm stable",
        "Aim for at least 7 hours of sleep every night",
    ),
    "activity": (
        "Start with short walks and gradually build up your daily activity",
        "Increase weekly exercise frequency, aiming for at least 150 minutes per week",
    ),
    "health": (
        "Take short breaks or try relaxation techniques to help lower stress",
        "Keep monitoring your vitals and maintain a balanced daily routine",
    ),
}
_LOW_SCORE_THRESHOLD = 60.0


def ranked_categories(category_scores: dict[Category, float | None]) -> list[tuple[Category, float]]:
    """Categories with a known score, weakest (lowest score) first."""
    return sorted(
        ((category, score) for category, score in category_scores.items() if score is not None),
        key=lambda item: item[1],
    )


def build_suggestions(category_scores: dict[Category, float | None]) -> dict[str, str]:
    """Static fallback: picks the two lowest-scoring categories and returns one canned tip
    for each, ranked worst first (key "1" = weakest). Used when AI suggestion generation
    is unavailable or fails."""
    ranked = ranked_categories(category_scores)
    suggestions = {}
    for i, (category, score) in enumerate(ranked[:2]):
        low_tip, moderate_tip = _SUGGESTIONS[category]
        suggestions[str(i + 1)] = low_tip if score < _LOW_SCORE_THRESHOLD else moderate_tip
    return suggestions


_IMPROVEMENT_TARGET = 90.0
_CATEGORY_WEIGHT = 1 / 3


def estimate_improved_by(category_scores: dict[Category, float | None], overall_score: float | None) -> float:
    """Estimates the overall-score percentage gain from raising the two weakest categories
    up to a healthy target, weighted the same way summary_service combines them into an
    overall score (equal thirds), relative to the current overall score."""
    if not overall_score:
        return 0.0
    ranked = ranked_categories(category_scores)
    gains = [max(0.0, _IMPROVEMENT_TARGET - score) * _CATEGORY_WEIGHT for _, score in ranked[:2]]
    if not gains:
        return 0.0
    return round(sum(gains) / overall_score * 100, 1)
