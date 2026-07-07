import calendar
import json
from datetime import date, datetime, timedelta

from sqlalchemy.orm import Session

from src.core import ai_client
from src.core.logging import logger
from src.device.models.device_model import DeviceRecord
from src.device.models.health_model import HealthRecord
from src.health.schemas.health_trending_schema import HealthTrendingResponse, TrendPeriod
from src.health.services import trending_rules as rules
from src.health.services.errors import HealthError
from src.summary.models.summary_model import DailyHealthSummaryRecord
from src.summary.services import summary_service

_WEEK_DAYS = 7
_MONTH_WEEKS = 4
_YEAR_MONTHS = 12

DailyScores = tuple[float | None, float | None, float | None, float | None]  # sleep, activity, health, overall

_SUGGESTION_SYSTEM_PROMPT = """You are a health data analysis assistant. You will receive a period's overall
health score_label, its latest score and trend, and its two weakest-scoring categories (from sleep, activity,
health) with their scores. Return a JSON object with exactly two keys, "1" and "2" (one per weakest category
given, "1" = the weakest), each mapping to an object with exactly three keys:
{
  "1": {"issue": "<string>", "solution": "<string>", "improvement": "<string>"},
  "2": {"issue": "<string>", "solution": "<string>", "improvement": "<string>"}
}
Field meanings:
- "issue": names which indicator is currently a problem and briefly why, referencing the given score.
- "solution": a short, concrete, actionable step to address it.
- "improvement": how following the solution could raise the score (qualitative, do not fabricate precise numbers).
Rules:
- Do not diagnose disease or recommend medication or medical treatment.
- Base everything only on the provided data.
- Return JSON only."""


def _parse_ai_suggestions(result: dict, expected_keys: int) -> dict[str, dict[str, str]] | None:
    parsed = {}
    for key in ("1", "2")[:expected_keys]:
        entry = result.get(key)
        if not isinstance(entry, dict):
            return None
        issue, solution, improvement = entry.get("issue"), entry.get("solution"), entry.get("improvement")
        if not (issue and solution and improvement):
            return None
        parsed[key] = {"issue": issue, "solution": solution, "improvement": improvement}
    return parsed


def _generate_ai_suggestions(
    category_scores: dict[str, float | None], score_label: str, scores: list[float], language: str
) -> dict[str, dict[str, str]]:
    ranked = rules.ranked_categories(category_scores)
    if not ranked:
        return {}
    payload = {
        "score_label": score_label,
        "latest_score": scores[-1],
        "trend": round(scores[-1] - scores[0], 1),
        "weakest_categories": [{"category": c, "score": s} for c, s in ranked[:2]],
    }
    prompt = ai_client.with_language(_SUGGESTION_SYSTEM_PROMPT, language)
    try:
        result, _usage = ai_client.generate_json(prompt, f"Input:\n{json.dumps(payload, default=str)}")
        parsed = _parse_ai_suggestions(result, min(2, len(ranked)))
        if parsed is not None:
            return parsed
    except Exception:  # noqa: BLE001
        logger.exception("AI trending suggestion generation failed")
    return rules.build_suggestions(category_scores)


def _date_range(end_date: date, days: int) -> list[str]:
    return [(end_date - timedelta(days=i)).isoformat() for i in range(days - 1, -1, -1)]


def _weekly_buckets(end_date: date, weeks: int) -> list[str]:
    """Ascending list of each weekly bucket's end date (inclusive), the most recent bucket
    ending exactly on end_date."""
    return [(end_date - timedelta(weeks=i)).isoformat() for i in range(weeks - 1, -1, -1)]


def _monthly_buckets(end_date: date, months: int) -> list[str]:
    """Ascending list of "yyyy-mm" calendar months, ending at end_date's month."""
    buckets = []
    for i in range(months - 1, -1, -1):
        month_index = end_date.month - 1 - i
        year = end_date.year + month_index // 12
        month = month_index % 12 + 1
        buckets.append(f"{year:04d}-{month:02d}")
    return buckets


def _dates_in_month(year_month: str, end_date: date) -> list[str]:
    """All calendar dates in the given "yyyy-mm" month, capped at end_date for the current
    month so future dates are never included."""
    year, month = (int(part) for part in year_month.split("-"))
    last_day = calendar.monthrange(year, month)[1]
    month_start = date(year, month, 1)
    month_end = min(date(year, month, last_day), end_date)
    if month_end < month_start:
        return []
    return [(month_start + timedelta(days=i)).isoformat() for i in range((month_end - month_start).days + 1)]


def _average(values: list[float]) -> float | None:
    if not values:
        return None
    return round(sum(values) / len(values), 1)


def _health_record_dates(db: Session, device_id: int, dates: list[str]) -> list[str]:
    """The subset of `dates` that actually have a HealthRecord row — health is the anchor for
    which dates count as "a day" in trending, since sleep/activity can be uploaded under a
    slightly different date (e.g. a sleep session spanning past midnight)."""
    rows = (
        db.query(HealthRecord.date)
        .filter(HealthRecord.device_id == device_id, HealthRecord.date.in_(dates))
        .all()
    )
    present = {row[0] for row in rows}
    return [d for d in dates if d in present]


def _daily_scores_for_dates(db: Session, device_id: int, dates: list[str]) -> dict[str, DailyScores]:
    """(sleep_score, activity_score, health_score, overall_score) per date, preferring the
    cached DailyHealthSummaryRecord row already written by /v1/summary, and falling back to a
    live, on-the-fly deterministic computation from the raw records for any date not cached
    yet — so trending works even for devices that never had /v1/summary called on them."""
    cached_rows = (
        db.query(DailyHealthSummaryRecord)
        .filter(DailyHealthSummaryRecord.device_id == device_id, DailyHealthSummaryRecord.date.in_(dates))
        .all()
    )
    result: dict[str, DailyScores] = {
        row.date: (row.sleep_score, row.activity_score, row.health_score, row.overall_score) for row in cached_rows
    }
    missing = [d for d in dates if d not in result]
    if missing:
        result.update(summary_service.compute_daily_scores_batch(db, device_id, missing))
    return result


def _latest_category_scores(db: Session, device_id: int, on_date: str | None) -> dict[str, float | None]:
    if on_date is None:
        return {"sleep": None, "activity": None, "health": None}
    sleep_score, activity_score, health_score, _overall = _daily_scores_for_dates(db, device_id, [on_date]).get(
        on_date, (None, None, None, None)
    )
    return {"sleep": sleep_score, "activity": activity_score, "health": health_score}


def _build_period(
    db: Session,
    device_id: int,
    labels: list[str],
    scores: list[float],
    latest_date: str,
    language: str,
    notes: dict[str, str],
) -> TrendPeriod:
    category_scores = _latest_category_scores(db, device_id, latest_date)
    score_label = rules.classify_score_label(scores)
    return TrendPeriod(
        date=", ".join(labels),
        score=scores,
        score_label=score_label,
        suggestion=_generate_ai_suggestions(category_scores, score_label, scores, language),
        improved_by=rules.estimate_improved_by(category_scores, scores[-1]),
        notes=notes,
    )


def _week_period(db: Session, device_id: int, end_date: date, language: str) -> TrendPeriod:
    health_dates = _health_record_dates(db, device_id, _date_range(end_date, _WEEK_DAYS))
    if not health_dates:
        raise HealthError(404, "近7天無健康分數資料，無法產生週趨勢")

    daily = _daily_scores_for_dates(db, device_id, health_dates)
    labels, scores, notes = [], [], {}
    for d in health_dates:
        sleep_score, activity_score, health_score, overall = daily.get(d, (None, None, None, None))
        if overall is None:
            continue
        labels.append(d)
        scores.append(overall)
        note = rules.missing_data_note(sleep_score, activity_score, health_score)
        if note:
            notes[d] = note
    if not scores:
        raise HealthError(404, "近7天無健康分數資料，無法產生週趨勢")
    return _build_period(db, device_id, labels, scores, labels[-1], language, notes)


def _month_period(db: Session, device_id: int, end_date: date, language: str) -> TrendPeriod:
    labels, scores, notes, latest_date = [], [], {}, None
    for bucket_end in _weekly_buckets(end_date, _MONTH_WEEKS):
        bucket_dates = _date_range(date.fromisoformat(bucket_end), _WEEK_DAYS)
        health_dates = _health_record_dates(db, device_id, bucket_dates)
        if not health_dates:
            continue

        daily = _daily_scores_for_dates(db, device_id, health_dates)
        bucket_scores, incomplete = [], False
        for d in health_dates:
            sleep_score, activity_score, health_score, overall = daily.get(d, (None, None, None, None))
            if overall is None:
                continue
            bucket_scores.append(overall)
            if rules.missing_data_note(sleep_score, activity_score, health_score):
                incomplete = True
        if not bucket_scores:
            continue

        labels.append(bucket_end)
        scores.append(_average(bucket_scores))
        if incomplete:
            notes[bucket_end] = "此區間內部分日期資料不足，分數可能不完整"
        bucket_latest = max(health_dates)
        if latest_date is None or bucket_latest > latest_date:
            latest_date = bucket_latest
    if not scores:
        raise HealthError(404, "近期無健康分數資料，無法產生月趨勢")
    return _build_period(db, device_id, labels, scores, latest_date, language, notes)


def _year_period(db: Session, device_id: int, end_date: date, language: str) -> TrendPeriod:
    labels, scores, notes, latest_date = [], [], {}, None
    for year_month in _monthly_buckets(end_date, _YEAR_MONTHS):
        health_dates = _health_record_dates(db, device_id, _dates_in_month(year_month, end_date))
        if not health_dates:
            continue

        daily = _daily_scores_for_dates(db, device_id, health_dates)
        bucket_scores, incomplete = [], False
        for d in health_dates:
            sleep_score, activity_score, health_score, overall = daily.get(d, (None, None, None, None))
            if overall is None:
                continue
            bucket_scores.append(overall)
            if rules.missing_data_note(sleep_score, activity_score, health_score):
                incomplete = True
        if not bucket_scores:
            continue

        labels.append(year_month)
        scores.append(_average(bucket_scores))
        if incomplete:
            notes[year_month] = "此區間內部分日期資料不足，分數可能不完整"
        month_latest = max(health_dates)
        if latest_date is None or month_latest > latest_date:
            latest_date = month_latest
    if not scores:
        raise HealthError(404, "近一年無健康分數資料，無法產生年趨勢")
    return _build_period(db, device_id, labels, scores, latest_date, language, notes)


def get_health_trending(
    db: Session, mac_address: str, date_str: str, language: str = "en"
) -> HealthTrendingResponse:
    device = db.query(DeviceRecord).filter(DeviceRecord.mac_address == mac_address).first()
    if device is None:
        raise HealthError(404, "找不到對應設備")

    try:
        end_date = datetime.strptime(date_str, "%Y-%m-%d").date()
    except ValueError as e:
        raise HealthError(400, "date 格式錯誤，需為 yyyy-mm-dd") from e

    return HealthTrendingResponse(
        week=_week_period(db, device.id, end_date, language),
        month=_month_period(db, device.id, end_date, language),
        year=_year_period(db, device.id, end_date, language),
    )
