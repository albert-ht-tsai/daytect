from datetime import date as date_cls
from datetime import datetime, timezone

from fastapi import BackgroundTasks
from sqlalchemy.orm import Session

from src.dashboard.schemas.dashboard_schema import (
    CurrentDevice,
    CurrentHealthReport,
    DashboardAnalysisStatus,
    DashboardChartPoint,
    DashboardHealthInsight,
    DashboardHealthScore,
    DashboardHealthTrend,
    DashboardResponse,
    DeviceRangeAlert,
    HealthInsightItem,
    Navigation,
    ViewDetail,
    ViewDetailParams,
)
from src.health.analysis.services import analysis_service, period_stats
from src.health.analysis.services.status_messages import status_message
from src.user_device.models.device_model import Device

_METRIC_ORDER = ["heart_rate", "blood_pressure", "blood_oxygen", "sleep", "body_temperature", "activity"]
_METRIC_LABELS = {
    "heart_rate": "Heart Rate",
    "blood_pressure": "Blood Pressure",
    "blood_oxygen": "SpO₂",
    "sleep": "Sleep",
    "body_temperature": "Body Temperature",
    "activity": "Activity",
}


def _format_value(metric: str, metric_values: dict) -> str | None:
    if metric == "heart_rate":
        v = metric_values.get("heart_rate")
        return f"{round(v)} bpm" if v is not None else None
    if metric == "blood_pressure":
        bp = metric_values.get("blood_pressure") or {}
        if bp.get("systolic") is None:
            return None
        return f"{round(bp['systolic'])}/{round(bp['diastolic'])} mmHg"
    if metric == "blood_oxygen":
        v = metric_values.get("blood_oxygen")
        return f"{round(v)}%" if v is not None else None
    if metric == "sleep":
        minutes = metric_values.get("sleep_minutes")
        if minutes is None:
            return None
        return f"{int(minutes // 60)}h {int(minutes % 60)}m"
    if metric == "body_temperature":
        v = metric_values.get("body_temperature")
        return f"{round(v, 1)}°C" if v is not None else None
    if metric == "activity":
        steps = metric_values.get("steps")
        return f"{round(steps / 1000, 1)}k steps" if steps is not None else None
    return None


def _build_health_insight(content: dict, generated_at) -> DashboardHealthInsight:
    metric_values = content.get("metric_values", {})
    metric_statuses = content.get("metric_statuses", {})
    metric_messages = content.get("metric_messages", {})

    items = [
        HealthInsightItem(
            metric=metric,
            label=_METRIC_LABELS[metric],
            value=_format_value(metric, metric_values),
            status=metric_statuses.get(metric),
            message=metric_messages.get(metric),
        )
        for metric in _METRIC_ORDER
    ]

    return DashboardHealthInsight(
        status="ready",
        generated_by=analysis_service.GENERATED_BY,
        updated_at=generated_at,
        summary=content.get("summary", ""),
        items=items,
    )


def _device_range_alert(db: Session, device: Device) -> DeviceRangeAlert:
    now = datetime.now(timezone.utc)
    muted_until = device.alert_muted_until
    if muted_until and muted_until.tzinfo is None:
        muted_until = muted_until.replace(tzinfo=timezone.utc)
    is_muted = bool(muted_until and muted_until > now)
    is_out_of_range = device.bluetooth_status == "out_of_range"
    is_active = is_out_of_range and not is_muted

    if is_out_of_range:
        device.alert_last_triggered_at = now
        db.add(device)
        db.commit()

    return DeviceRangeAlert(
        is_active=is_active,
        status=device.bluetooth_status,
        title="Device Out of Range" if is_active else None,
        message=f"{device.name} may be out of Bluetooth range. Please bring it closer." if is_active else None,
        illustration_key="device_out_of_range" if is_active else None,
        remind_later_minutes=device.alert_remind_later_minutes,
        last_triggered_at=device.alert_last_triggered_at,
        muted_until=device.alert_muted_until,
    )


def get_dashboard(
    db: Session, device: Device, date_value: date_cls, background_tasks: BackgroundTasks
) -> DashboardResponse:
    analysis = analysis_service.get_or_create_analysis(db, device, "daily", date_value, date_value, background_tasks)

    analysis_status = DashboardAnalysisStatus(
        status=analysis.status,
        analysis_id=analysis.id if analysis.status == "ready" else None,
        generated_at=analysis.generated_at,
        message=status_message(analysis.status, "daily"),
    )

    current_health_report = None
    if analysis.status == "ready":
        content = analysis.content
        overall = content["overall_score"]
        level = overall["level"]
        chart = period_stats.daily_trend_chart(db, device.id, date_value)

        current_health_report = CurrentHealthReport(
            health_score=DashboardHealthScore(
                score=overall["score"],
                max_score=overall["max_score"],
                level=level,
                label=level.capitalize(),
                description=overall["description"],
                change=overall.get("change"),
            ),
            health_trend=DashboardHealthTrend(
                status=content["trend_summary"]["status"],
                summary=content["trend_summary"]["content"],
                chart_type="line",
                chart=[DashboardChartPoint(**point) for point in chart],
            ),
            health_insight=_build_health_insight(content, analysis.generated_at),
        )

    return DashboardResponse(
        device_id=device.id,
        date=date_value.isoformat(),
        generated_at=analysis.generated_at,
        current_device=CurrentDevice.model_validate(device),
        analysis_status=analysis_status,
        current_health_report=current_health_report,
        device_range_alert=_device_range_alert(db, device),
        navigation=Navigation(view_detail=ViewDetail(params=ViewDetailParams(device_id=device.id))),
    )
