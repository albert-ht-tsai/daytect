from datetime import date as date_cls
from datetime import datetime, timezone

from fastapi import APIRouter, BackgroundTasks, HTTPException, Query, status

from src.core.deps import CurrentUser, SessionDep
from src.report.schemas.report_schema import ReportResponse
from src.report.services import report_service
from src.user_device.services.device_service import get_owned_device

router = APIRouter(tags=["report"])


def _today() -> date_cls:
    return datetime.now(timezone.utc).date()


def _parse_date(value: str, default: date_cls) -> date_cls:
    try:
        return date_cls.fromisoformat(value)
    except ValueError:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, detail={"code": 400, "message": "Invalid date format"})


@router.get("/reports/{device_id}", response_model=ReportResponse)
def get_report_endpoint(
    device_id: int,
    db: SessionDep,
    current_user: CurrentUser,
    background_tasks: BackgroundTasks,
    range: str = Query(...),
    start_date: str = Query(...),
    end_date: str = Query(...),
):
    if range not in ("weekly", "monthly"):
        raise HTTPException(status.HTTP_400_BAD_REQUEST, detail={"code": 400, "message": "range must be weekly or monthly"})
    device = get_owned_device(db, current_user, device_id)
    start = _parse_date(start_date, _today())
    end = _parse_date(end_date, _today())
    return report_service.get_report(db, device, range, start, end, background_tasks)
