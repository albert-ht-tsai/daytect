from datetime import date as date_cls
from datetime import datetime, timezone

from fastapi import APIRouter, BackgroundTasks, HTTPException, Query, status

from src.core.deps import CurrentUser, SessionDep
from src.health.analysis.schemas.analysis_schema import (
    AnalysisStatusData,
    AvailableAnalysisDatesResponse,
    DailyAnalysisResponse,
    TriggerAnalysisData,
    TriggerAnalysisRequest,
)
from src.health.analysis.services import analysis_service
from src.user_device.services.device_service import get_owned_device

router = APIRouter(tags=["analysis"])


def _today() -> date_cls:
    return datetime.now(timezone.utc).date()


def _parse_date(value: str | None, default: date_cls) -> date_cls:
    if value is None:
        return default
    try:
        return date_cls.fromisoformat(value)
    except ValueError:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, detail={"code": 400, "message": "Invalid date format"})


@router.post("/analysis/{device_id}")
def trigger_analysis_endpoint(
    device_id: int,
    body: TriggerAnalysisRequest,
    db: SessionDep,
    current_user: CurrentUser,
    background_tasks: BackgroundTasks,
):
    device = get_owned_device(db, current_user, device_id)
    if body.range not in ("daily", "weekly", "monthly"):
        raise HTTPException(status.HTTP_400_BAD_REQUEST, detail={"code": 400, "message": "Invalid range"})
    date_value = _parse_date(body.date, _today())
    analysis = analysis_service.trigger(db, device, date_value, body.range, background_tasks)
    return {
        "success": True,
        "data": analysis_service.to_trigger_data(analysis),
        "message": "AI health analysis generation started.",
    }


@router.get("/analysis/{analysis_id}/status", response_model=AnalysisStatusData)
def get_analysis_status_endpoint(analysis_id: int, db: SessionDep, current_user: CurrentUser):
    analysis = analysis_service.get_status(db, current_user.id, analysis_id)
    return analysis_service.to_status_data(analysis)


@router.get("/analysis/{device_id}/dates", response_model=AvailableAnalysisDatesResponse)
def get_analysis_dates_endpoint(
    device_id: int, db: SessionDep, current_user: CurrentUser, range: str = Query(default="daily")
):
    device = get_owned_device(db, current_user, device_id)
    return AvailableAnalysisDatesResponse(range=range, dates=analysis_service.get_available_dates(db, device, range))


@router.get("/analysis/{device_id}", response_model=DailyAnalysisResponse)
def get_daily_analysis_endpoint(
    device_id: int,
    db: SessionDep,
    current_user: CurrentUser,
    background_tasks: BackgroundTasks,
    date: str | None = Query(default=None),
    range: str = Query(default="daily"),
):
    if range != "daily":
        raise HTTPException(
            status.HTTP_400_BAD_REQUEST,
            detail={"code": 400, "message": "Use /reports for weekly or monthly analysis"},
        )
    device = get_owned_device(db, current_user, device_id)
    date_value = _parse_date(date, _today())
    analysis = analysis_service.get_or_create_analysis(db, device, "daily", date_value, date_value, background_tasks)
    return analysis_service.to_daily_response(analysis)
