import json
from datetime import date, datetime, timedelta

from sqlalchemy.orm import Session

from src.core import ai_client
from src.core.logging import logger
from src.device.models.device_model import DeviceRecord
from src.health.schemas.health_trending_schema import HealthTrendingResponse, TrendPeriod
from src.health.services import trending_rules as rules
from src.health.services.errors import HealthError
from src.summary.models.summary_model import DailyHealthSummaryRecord

_WEEK_DAYS = 7
_MONTH_WEEKS = 4
_YEAR_MONTHS = 12

_SUGGESTION_SYSTEM_PROMPT = """You are a health data analysis assistant. You will receive a period's overall
health score_label, its latest score and trend, and its two weakest-scoring categories (from sleep, activity,
health) with their scores. Return a JSON object with exactly two keys:
{"1": "<string>", "2": "<string>"}
Rules:
- "1" addresses the weakest category given, "2" addresses the second weakest.
- Each suggestion must be a short, concrete, actionable tip (one sentence).
- Do not diagnose disease or recommend medication or medical treatment.
- Base suggestions only on the provided data.
- Return JSON only."""


def _generate_ai_suggestions(
    category_scores: dict[str, float | None], score_label: str, scores: list[float], language: str
) -> dict[str, str]:
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
        if result.get("1") and result.get("2"):
            return {"1": result["1"], "2": result["2"]}
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


def _average(values: list[float]) -> float | None:
    if not values:
        return None
    return round(sum(values) / len(values), 1)


def _daily_overall_scores(db: Session, device_id: int, dates: list[str]) -> dict[str, float]:
    rows = (
        db.query(DailyHealthSummaryRecord)
        .filter(
            DailyHealthSummaryRecord.device_id == device_id,
            DailyHealthSummaryRecord.date.in_(dates),
            DailyHealthSummaryRecord.overall_score.isnot(None),
        )
        .all()
    )
    return {row.date: row.overall_score for row in rows}


def _latest_category_scores(db: Session, device_id: int, on_date: str | None) -> dict[str, float | None]:
    record = None
    if on_date is not None:
        record = (
            db.query(DailyHealthSummaryRecord)
            .filter(DailyHealthSummaryRecord.device_id == device_id, DailyHealthSummaryRecord.date == on_date)
            .first()
        )
    if record is None:
        return {"sleep": None, "activity": None, "health": None}
    return {"sleep": record.sleep_score, "activity": record.activity_score, "health": record.health_score}


def _build_period(
    db: Session, device_id: int, labels: list[str], scores: list[float], latest_date: str, language: str
) -> TrendPeriod:
    category_scores = _latest_category_scores(db, device_id, latest_date)
    score_label = rules.classify_score_label(scores)
    return TrendPeriod(
        date=", ".join(labels),
        score=scores,
        score_label=score_label,
        suggestion=_generate_ai_suggestions(category_scores, score_label, scores, language),
        improved_by=rules.estimate_improved_by(category_scores, scores[-1]),
    )


def _week_period(db: Session, device_id: int, end_date: date, language: str) -> TrendPeriod:
    dates = _date_range(end_date, _WEEK_DAYS)
    scores_by_date = _daily_overall_scores(db, device_id, dates)
    ordered = [(d, scores_by_date[d]) for d in dates if d in scores_by_date]
    if not ordered:
        raise HealthError(404, "近7天無健康分數資料，無法產生週趨勢")
    labels = [d for d, _ in ordered]
    scores = [s for _, s in ordered]
    return _build_period(db, device_id, labels, scores, labels[-1], language)


def _month_period(db: Session, device_id: int, end_date: date, language: str) -> TrendPeriod:
    labels, scores, latest_date = [], [], None
    for bucket_end in _weekly_buckets(end_date, _MONTH_WEEKS):
        bucket_dates = _date_range(date.fromisoformat(bucket_end), _WEEK_DAYS)
        scores_by_date = _daily_overall_scores(db, device_id, bucket_dates)
        if not scores_by_date:
            continue
        labels.append(bucket_end)
        scores.append(_average(list(scores_by_date.values())))
        bucket_latest = max(scores_by_date)
        if latest_date is None or bucket_latest > latest_date:
            latest_date = bucket_latest
    if not scores:
        raise HealthError(404, "近期無健康分數資料，無法產生月趨勢")
    return _build_period(db, device_id, labels, scores, latest_date, language)


def _year_period(db: Session, device_id: int, end_date: date, language: str) -> TrendPeriod:
    labels, scores, latest_date = [], [], None
    for year_month in _monthly_buckets(end_date, _YEAR_MONTHS):
        rows = (
            db.query(DailyHealthSummaryRecord)
            .filter(
                DailyHealthSummaryRecord.device_id == device_id,
                DailyHealthSummaryRecord.date.like(f"{year_month}-%"),
                DailyHealthSummaryRecord.overall_score.isnot(None),
            )
            .all()
        )
        if not rows:
            continue
        labels.append(year_month)
        scores.append(_average([row.overall_score for row in rows]))
        month_latest = max(row.date for row in rows)
        if latest_date is None or month_latest > latest_date:
            latest_date = month_latest
    if not scores:
        raise HealthError(404, "近一年無健康分數資料，無法產生年趨勢")
    return _build_period(db, device_id, labels, scores, latest_date, language)


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
