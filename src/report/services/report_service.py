from datetime import date as date_cls

from fastapi import BackgroundTasks
from sqlalchemy.orm import Session

from src.health.analysis.services import analysis_service
from src.health.analysis.services.status_messages import status_message
from src.report.schemas.report_schema import HealthReport, ReportAnalysisStatus, ReportResponse
from src.user_device.models.device_model import Device


def get_report(
    db: Session,
    device: Device,
    range_: str,
    start_date: date_cls,
    end_date: date_cls,
    background_tasks: BackgroundTasks,
) -> ReportResponse:
    analysis = analysis_service.get_or_create_analysis(db, device, range_, start_date, end_date, background_tasks)

    analysis_status = ReportAnalysisStatus(
        status=analysis.status,
        analysis_id=analysis.id,
        generated_at=analysis.generated_at,
        message=status_message(analysis.status, range_),
    )

    health_report = HealthReport(**analysis.content) if analysis.status == "ready" else None

    return ReportResponse(
        device_id=device.id,
        range=range_,
        start_date=start_date.isoformat(),
        end_date=end_date.isoformat(),
        generated_at=analysis.generated_at,
        generated_by=analysis_service.GENERATED_BY if analysis.status == "ready" else None,
        analysis_status=analysis_status,
        health_report=health_report,
    )
