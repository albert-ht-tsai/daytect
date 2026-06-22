import json
from datetime import date as date_cls
from datetime import datetime, timedelta, timezone

from fastapi import BackgroundTasks, HTTPException, status
from sqlalchemy.orm import Session

from src.core.ai_client import generate_daily, generate_periodic
from src.core.database import engine
from src.core.logging import logger
from src.health.analysis.models.analysis_model import Analysis
from src.health.analysis.schemas.analysis_schema import (
    AnalysisStatusData,
    DailyAnalysisResponse,
    DailyAnalysisStatus,
    TriggerAnalysisData,
)
from src.health.analysis.services import period_stats
from src.health.analysis.services.status_messages import status_message
from src.health.models.health_record_model import HealthRecord
from src.health.services import health_metrics
from src.health.services.health_service import average_heart_rate, compute_metric_statuses
from src.user_device.models.device_model import Device

GENERATED_BY = "Daytect AI"


def to_daily_response(analysis: Analysis) -> DailyAnalysisResponse:
    content = analysis.content or {}
    return DailyAnalysisResponse(
        analysis_id=analysis.id if analysis.status == "ready" else None,
        device_id=analysis.device_id,
        date=analysis.start_date.isoformat(),
        range="daily",
        generated_by=GENERATED_BY if analysis.status == "ready" else None,
        generated_at=analysis.generated_at,
        analysis_status=DailyAnalysisStatus(status=analysis.status, message=status_message(analysis.status, "daily")),
        summary=content.get("summary"),
        overall_score=content.get("overall_score"),
        trend_summary=content.get("trend_summary"),
        abnormalities=content.get("abnormalities"),
        key_insights=content.get("key_insights"),
        recommendations=content.get("recommendations"),
    )


def to_status_data(analysis: Analysis) -> AnalysisStatusData:
    return AnalysisStatusData(
        analysis_id=analysis.id,
        device_id=analysis.device_id,
        range=analysis.range,
        status=analysis.status,
        generated_at=analysis.generated_at,
        message=status_message(analysis.status, analysis.range),
    )


def to_trigger_data(analysis: Analysis) -> TriggerAnalysisData:
    return TriggerAnalysisData(
        analysis_id=analysis.id,
        device_id=analysis.device_id,
        date=analysis.start_date.isoformat(),
        range=analysis.range,
        status=analysis.status,
    )


def period_bounds(date_value: date_cls, range_: str) -> tuple[date_cls, date_cls]:
    if range_ == "daily":
        return date_value, date_value
    if range_ == "weekly":
        return date_value - timedelta(days=6), date_value
    if range_ == "monthly":
        return period_stats.month_bounds(date_value)
    raise HTTPException(status.HTTP_400_BAD_REQUEST, detail={"code": 400, "message": "range must be daily, weekly, or monthly"})


def _existing(db: Session, device_id: int, range_: str, start_date: date_cls, end_date: date_cls) -> Analysis | None:
    return (
        db.query(Analysis)
        .filter(
            Analysis.device_id == device_id,
            Analysis.range == range_,
            Analysis.start_date == start_date,
            Analysis.end_date == end_date,
        )
        .first()
    )


def _has_data(db: Session, device_id: int, start_date: date_cls, end_date: date_cls) -> bool:
    return (
        db.query(HealthRecord.id)
        .filter(HealthRecord.device_id == device_id, HealthRecord.date >= start_date, HealthRecord.date <= end_date)
        .first()
        is not None
    )


def get_or_create_analysis(
    db: Session,
    device: Device,
    range_: str,
    start_date: date_cls,
    end_date: date_cls,
    background_tasks: BackgroundTasks,
) -> Analysis:
    analysis = _existing(db, device.id, range_, start_date, end_date)
    if analysis:
        return analysis

    if not _has_data(db, device.id, start_date, end_date):
        analysis = Analysis(
            device_id=device.id, range=range_, start_date=start_date, end_date=end_date, status="not_enough_data"
        )
        db.add(analysis)
        db.commit()
        db.refresh(analysis)
        return analysis

    analysis = Analysis(device_id=device.id, range=range_, start_date=start_date, end_date=end_date, status="processing")
    db.add(analysis)
    db.commit()
    db.refresh(analysis)
    background_tasks.add_task(run_generation, analysis.id)
    return analysis


def trigger(
    db: Session, device: Device, date_value: date_cls, range_: str, background_tasks: BackgroundTasks
) -> Analysis:
    start_date, end_date = period_bounds(date_value, range_)
    analysis = _existing(db, device.id, range_, start_date, end_date)
    has_data = _has_data(db, device.id, start_date, end_date)

    if analysis is None:
        analysis = Analysis(device_id=device.id, range=range_, start_date=start_date, end_date=end_date)
        db.add(analysis)

    if not has_data:
        analysis.status = "not_enough_data"
        analysis.content = None
        db.commit()
        db.refresh(analysis)
        return analysis

    analysis.status = "processing"
    analysis.content = None
    analysis.error_message = None
    analysis.generated_at = None
    db.commit()
    db.refresh(analysis)
    background_tasks.add_task(run_generation, analysis.id)
    return analysis


def get_status(db: Session, user_id: int, analysis_id: int) -> Analysis:
    analysis = (
        db.query(Analysis)
        .join(Device, Device.id == Analysis.device_id)
        .filter(Analysis.id == analysis_id, Device.user_id == user_id)
        .first()
    )
    if not analysis:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail={"code": 404, "message": "Analysis not found"})
    return analysis


def get_available_dates(db: Session, device: Device, range_: str) -> list[str]:
    rows = (
        db.query(Analysis.end_date)
        .filter(Analysis.device_id == device.id, Analysis.range == range_)
        .order_by(Analysis.end_date.desc())
        .all()
    )
    return [row[0].isoformat() for row in rows]


def run_generation(analysis_id: int) -> None:
    with Session(engine) as db:
        analysis = db.query(Analysis).filter(Analysis.id == analysis_id).first()
        if analysis is None:
            return
        try:
            if analysis.range == "daily":
                content = _generate_daily_content(db, analysis)
            else:
                content = _generate_periodic_content(db, analysis)
            analysis.content = content
            analysis.status = "ready"
            analysis.generated_at = datetime.now(timezone.utc)
        except Exception as e:
            logger.exception("Analysis generation failed for analysis_id=%s", analysis_id)
            analysis.status = "failed"
            analysis.error_message = str(e)[:500]
        db.commit()


def _build_daily_prompt(date_value, metric_values, statuses, score, level, trend_status) -> str:
    return (
        f"Analyze this user's wearable health data for {date_value.isoformat()}.\n"
        f"Overall health score: {score}/100 ({level}). Trend vs previous day: {trend_status}.\n"
        f"Metric values: {json.dumps(metric_values, default=str)}\n"
        f"Metric statuses: {json.dumps(statuses)}\n"
        "Return strictly a JSON object with exactly these keys:\n"
        '- "summary": 1-2 sentence overall summary of the day\n'
        '- "overall_score_description": 1 short sentence describing the overall score\n'
        '- "trend_summary": 1 short sentence describing today\'s trend vs yesterday\n'
        '- "abnormalities": array of {"metric","level","content"} for metrics whose status is not '
        '"good" or "normal" (level one of monitor/warning/critical; empty array if none)\n'
        '- "key_insights": array of 2-4 {"title","content","status"} objects highlighting notable findings\n'
        '- "recommendations": array of 3-4 short actionable recommendation strings\n'
        '- "metric_messages": object with one short sentence message for each of '
        "heart_rate, blood_pressure, blood_oxygen, sleep, body_temperature, activity\n"
    )


def _generate_daily_content(db: Session, analysis: Analysis) -> dict:
    record = (
        db.query(HealthRecord)
        .filter(HealthRecord.device_id == analysis.device_id, HealthRecord.date == analysis.start_date)
        .first()
    )
    statuses = compute_metric_statuses(record)
    score, level = health_metrics.compute_health_score(statuses)

    previous = (
        db.query(HealthRecord)
        .filter(HealthRecord.device_id == analysis.device_id, HealthRecord.date < analysis.start_date)
        .order_by(HealthRecord.date.desc())
        .first()
    )
    trend_status = "stable"
    score_change = None
    if previous:
        prev_score, _ = health_metrics.compute_health_score(compute_metric_statuses(previous))
        diff = score - prev_score
        if diff > 0:
            trend_status = "improving"
        elif diff < 0:
            trend_status = "declining"
        score_change = {
            "value": abs(diff),
            "compare_to": "yesterday",
            "direction": "up" if diff > 0 else "down" if diff < 0 else "stable",
            "label": f"{'+' if diff >= 0 else ''}{diff} vs yesterday",
        }

    metric_values = {
        "heart_rate": average_heart_rate(record),
        "hrv": (record.hrv or {}).get("value"),
        "blood_pressure": record.blood_pressure,
        "blood_oxygen": (record.blood_oxygen or {}).get("value"),
        "sleep_minutes": (record.sleep or {}).get("total"),
        "body_temperature": (record.body_temperature or {}).get("value"),
        "steps": (record.activity or {}).get("steps"),
    }

    prompt = _build_daily_prompt(analysis.start_date, metric_values, statuses, score, level, trend_status)
    ai = generate_daily(prompt)

    return {
        "summary": ai.get("summary", ""),
        "overall_score": {
            "score": score,
            "max_score": 100,
            "level": level,
            "description": ai.get("overall_score_description", f"Your overall health is {level}."),
            "change": score_change,
        },
        "trend_summary": {"status": trend_status, "content": ai.get("trend_summary", "")},
        "abnormalities": ai.get("abnormalities", []),
        "key_insights": ai.get("key_insights", []),
        "recommendations": ai.get("recommendations", []),
        "metric_messages": ai.get("metric_messages", {}),
        "metric_statuses": statuses,
        "metric_values": metric_values,
    }


def _build_periodic_prompt(range_, period_label, score, level, trend_status, metric_summary) -> str:
    return (
        f"Analyze this user's {range_} wearable health report for {period_label}.\n"
        f"Overall health score: {score}/100 ({level}). Trend vs previous period: {trend_status}.\n"
        f"Per-metric summary: {json.dumps(metric_summary)}\n"
        "Return strictly a JSON object with exactly these keys:\n"
        '- "health_score_description": 1 short sentence describing the overall score\n'
        '- "trend_summary": 1 short sentence describing the trend vs the previous period\n'
        '- "insight_summary": 1-2 sentence overall summary\n'
        '- "sections": array of exactly 3 objects {"type","title","status","content"} for '
        'type="improvement"/title="Improvement", type="critical_signal"/title="Critical Signals", '
        'type="recommendation"/title="Recommendation"\n'
        '- "possible_contributors": array of 0-3 {"type","label","severity","description"} objects '
        "for notable risk factors (empty array if none)\n"
        '- "recommendations": array of 3-4 short actionable recommendation strings\n'
    )


def _generate_periodic_content(db: Session, analysis: Analysis) -> dict:
    records = period_stats.records_in_period(db, analysis.device_id, analysis.start_date, analysis.end_date)
    scores = [period_stats.record_score(r) for r in records]
    score = round(sum(scores) / len(scores))
    level = health_metrics.level_from_score(score)

    if analysis.range == "weekly":
        prev_start = analysis.start_date - timedelta(days=7)
        prev_end = analysis.start_date - timedelta(days=1)
        chart = period_stats.weekly_chart(records)
        chart_type = "bar"
        title = "Weekly Health Report"
        period_label = f"{analysis.start_date.strftime('%b %d')} - {analysis.end_date.strftime('%b %d, %Y')}"
        compare_to = "last_week"
    else:
        prev_month_end = analysis.start_date - timedelta(days=1)
        prev_start, prev_end = period_stats.month_bounds(prev_month_end)
        chart = period_stats.monthly_chart(records, analysis.start_date, analysis.end_date)
        chart_type = "line"
        title = "Monthly Health Report"
        period_label = analysis.start_date.strftime("%B %Y")
        compare_to = "last_month"

    prev_records = period_stats.records_in_period(db, analysis.device_id, prev_start, prev_end)
    change = None
    trend_status = "stable"
    if prev_records:
        prev_scores = [period_stats.record_score(r) for r in prev_records]
        prev_score = round(sum(prev_scores) / len(prev_scores))
        diff = score - prev_score
        direction = "up" if diff > 0 else "down" if diff < 0 else "stable"
        trend_status = "improving" if direction == "up" else "declining" if direction == "down" else "stable"
        change = {
            "value": abs(diff),
            "compare_to": compare_to,
            "direction": direction,
            "label": f"{'+' if diff >= 0 else ''}{diff} vs {compare_to.replace('_', ' ')}",
        }

    summary = period_stats.metric_summary(records)
    prompt = _build_periodic_prompt(analysis.range, period_label, score, level, trend_status, summary)
    ai = generate_periodic(prompt)

    return {
        "title": title,
        "period_label": period_label,
        "health_score": {
            "score": score,
            "max_score": 100,
            "level": level,
            "label": level.capitalize(),
            "description": ai.get("health_score_description", f"Your {analysis.range} health condition is {level}."),
            "change": change,
        },
        "health_trend": {
            "status": trend_status,
            "summary": ai.get("trend_summary", ""),
            "chart_type": chart_type,
            "chart": chart,
        },
        "health_insight": {
            "summary": ai.get("insight_summary", ""),
            "sections": ai.get("sections", []),
        },
        "metric_summary": summary,
        "possible_contributors": ai.get("possible_contributors", []),
        "recommendations": ai.get("recommendations", []),
    }
