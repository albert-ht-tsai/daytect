import calendar
from datetime import date as date_cls
from datetime import timedelta

from sqlalchemy.orm import Session

from src.health.models.health_record_model import HealthRecord
from src.health.services import health_metrics
from src.health.services.health_service import average_heart_rate, compute_metric_statuses

_METRIC_LABELS = {
    "sleep": "Sleep",
    "heart_rate": "Resting Heart Rate",
    "blood_pressure": "Blood Pressure",
    "blood_oxygen": "SpO₂",
    "body_temperature": "Body Temperature",
    "activity": "Activity",
}

_DAY_LABELS = ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"]


def records_in_period(db: Session, device_id: int, start_date: date_cls, end_date: date_cls) -> list[HealthRecord]:
    return (
        db.query(HealthRecord)
        .filter(HealthRecord.device_id == device_id, HealthRecord.date >= start_date, HealthRecord.date <= end_date)
        .order_by(HealthRecord.date.asc())
        .all()
    )


def record_score(record: HealthRecord) -> int:
    statuses = compute_metric_statuses(record)
    score, _ = health_metrics.compute_health_score(statuses)
    return score


def risk_level_from_score(score: int) -> str:
    if score >= 75:
        return "low"
    if score >= 60:
        return "moderate"
    if score >= 40:
        return "high"
    return "critical"


def daily_trend_chart(db: Session, device_id: int, end_date: date_cls, days: int = 5) -> list[dict]:
    start_date = end_date - timedelta(days=days - 1)
    records = {r.date: r for r in records_in_period(db, device_id, start_date, end_date)}
    chart = []
    for offset in range(days):
        d = start_date + timedelta(days=offset)
        record = records.get(d)
        if record is None:
            continue
        label = "Today" if d == end_date else f"{d.strftime('%b')} {d.day}"
        chart.append({"date": d.isoformat(), "label": label, "score": record_score(record)})
    return chart


def weekly_chart(records: list[HealthRecord]) -> list[dict]:
    chart = []
    for record in records:
        score = record_score(record)
        chart.append(
            {
                "date": record.date.isoformat(),
                "label": _DAY_LABELS[record.date.weekday()],
                "score": score,
                "risk_level": risk_level_from_score(score),
            }
        )
    return chart


def monthly_chart(records: list[HealthRecord], start_date: date_cls, end_date: date_cls) -> list[dict]:
    buckets: dict[int, list[HealthRecord]] = {}
    for record in records:
        week_index = (record.date - start_date).days // 7
        buckets.setdefault(week_index, []).append(record)

    chart = []
    for week_index in sorted(buckets.keys()):
        week_records = buckets[week_index]
        scores = [record_score(r) for r in week_records]
        avg_score = round(sum(scores) / len(scores))
        bucket_start = start_date + timedelta(days=week_index * 7)
        chart.append(
            {
                "date": bucket_start.isoformat(),
                "label": f"Week {week_index + 1}",
                "score": avg_score,
                "risk_level": risk_level_from_score(avg_score),
            }
        )
    return chart


def _format_average(metric: str, values: list[dict]) -> str:
    if metric == "sleep":
        avg_total = sum(v.get("total", 0) or 0 for v in values) / len(values)
        return f"{int(avg_total // 60)}h {int(avg_total % 60)}m"
    if metric == "heart_rate":
        avg = sum(values) / len(values)
        return f"{round(avg)} bpm"
    if metric == "blood_pressure":
        avg_sys = sum(v.get("systolic", 0) or 0 for v in values) / len(values)
        avg_dia = sum(v.get("diastolic", 0) or 0 for v in values) / len(values)
        return f"{round(avg_sys)}/{round(avg_dia)} mmHg"
    if metric == "blood_oxygen":
        avg = sum(v.get("value", 0) or 0 for v in values) / len(values)
        return f"{round(avg)}%"
    if metric == "body_temperature":
        avg = sum(v.get("value", 0) or 0 for v in values) / len(values)
        return f"{round(avg, 1)}°C"
    if metric == "activity":
        avg = sum(v.get("steps", 0) or 0 for v in values) / len(values)
        return f"{round(avg / 1000, 1)}k steps"
    return ""


def _trend_direction(first_half_avg: float, second_half_avg: float) -> str:
    if first_half_avg == 0:
        return "stable"
    if second_half_avg > first_half_avg * 1.02:
        return "up"
    if second_half_avg < first_half_avg * 0.98:
        return "down"
    return "stable"


def metric_summary(records: list[HealthRecord]) -> list[dict]:
    if not records:
        return []

    summary = []
    for metric in ("sleep", "heart_rate", "blood_pressure", "blood_oxygen", "body_temperature", "activity"):
        if metric == "heart_rate":
            raw_values = [average_heart_rate(r) for r in records if average_heart_rate(r) is not None]
        else:
            raw_values = [getattr(r, metric) for r in records if getattr(r, metric)]

        if not raw_values:
            continue

        mid = max(1, len(raw_values) // 2)
        first_half, second_half = raw_values[:mid], raw_values[mid:] or raw_values[:mid]

        def _scalar(v):
            if metric == "heart_rate":
                return v
            if metric == "sleep":
                return v.get("total", 0) or 0
            if metric == "blood_pressure":
                return v.get("systolic", 0) or 0
            if metric == "blood_oxygen" or metric == "body_temperature":
                return v.get("value", 0) or 0
            if metric == "activity":
                return v.get("steps", 0) or 0
            return 0

        trend = _trend_direction(
            sum(_scalar(v) for v in first_half) / len(first_half),
            sum(_scalar(v) for v in second_half) / len(second_half),
        )

        statuses_for_metric = []
        for r in records:
            s = compute_metric_statuses(r).get(metric)
            if s:
                statuses_for_metric.append(s)
        status = statuses_for_metric[-1] if statuses_for_metric else "normal"

        trend_phrase = {
            "up": "increased compared with the previous period",
            "down": "decreased compared with the previous period",
            "stable": "remained stable this period",
        }[trend]

        summary.append(
            {
                "metric": metric,
                "label": _METRIC_LABELS[metric],
                "average": _format_average(metric, raw_values),
                "status": status,
                "trend": trend,
                "description": f"{_METRIC_LABELS[metric]} {trend_phrase}.",
            }
        )

    return summary


def month_bounds(any_date: date_cls) -> tuple[date_cls, date_cls]:
    last_day = calendar.monthrange(any_date.year, any_date.month)[1]
    return any_date.replace(day=1), any_date.replace(day=last_day)
