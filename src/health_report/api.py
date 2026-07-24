from fastapi import APIRouter, BackgroundTasks
from fastapi.responses import JSONResponse

from src.core.deps import CurrentUserId, SessionDep
from src.health_report.schemas.health_report_schema import HealthReportCreateRequest
from src.health_report.services import health_report_service
from src.health_report.services.errors import HealthReportError

router = APIRouter(prefix="/health-reports", tags=["health-reports"])


def _error_response(error: HealthReportError) -> JSONResponse:
    return JSONResponse(
        status_code=error.status_code,
        content={"success": False, "error": {"code": error.code, "message": error.message}},
    )


def _load_owned_report(db: SessionDep, report_id: str, user_id: int):
    record = health_report_service.get_report_record(db, report_id)
    if record is None:
        raise HealthReportError(404, "找不到指定的報告", code="REPORT_NOT_FOUND")
    if record.user_id != user_id:
        raise HealthReportError(403, "無權存取此報告", code="FORBIDDEN")
    return record


@router.post("")
def create_health_report_endpoint(
    body: HealthReportCreateRequest,
    db: SessionDep,
    background_tasks: BackgroundTasks,
    user_id: CurrentUserId,
):
    try:
        record = health_report_service.create_report(db, user_id, body)
    except HealthReportError as e:
        return _error_response(e)

    background_tasks.add_task(health_report_service.run_generation, record.report_id)

    return {
        "success": True,
        "data": {
            "report_id": record.report_id,
            "job_id": record.report_id,
            "status": record.status,
            "progress": record.progress,
            "poll_interval_seconds": 10,
        },
    }


@router.get("/{report_id}/status")
def get_health_report_status_endpoint(report_id: str, db: SessionDep, user_id: CurrentUserId):
    try:
        record = _load_owned_report(db, report_id, user_id)
    except HealthReportError as e:
        return _error_response(e)
    return health_report_service.status_payload(record)


@router.get("/{report_id}")
def get_health_report_endpoint(report_id: str, db: SessionDep, user_id: CurrentUserId):
    try:
        record = _load_owned_report(db, report_id, user_id)
    except HealthReportError as e:
        return _error_response(e)
    if record.status != "completed":
        return _error_response(HealthReportError(409, "報告尚未產生完成", code="REPORT_NOT_READY"))
    return {"success": True, "data": record.payload}
