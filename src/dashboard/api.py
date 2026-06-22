from datetime import date as date_cls
from datetime import datetime, timezone

from fastapi import APIRouter, BackgroundTasks, HTTPException, Query, status

from src.core.deps import CurrentUser, SessionDep
from src.dashboard.schemas.dashboard_schema import DashboardResponse
from src.dashboard.services import dashboard_service
from src.user_device.services.device_service import get_owned_device

router = APIRouter(tags=["dashboard"])


def _today() -> date_cls:
    return datetime.now(timezone.utc).date()


def _parse_date(value: str | None, default: date_cls) -> date_cls:
    if value is None:
        return default
    try:
        return date_cls.fromisoformat(value)
    except ValueError:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, detail={"code": 400, "message": "Invalid date format"})


@router.get("/dashboard/{device_id}", response_model=DashboardResponse)
def get_dashboard_endpoint(
    device_id: int,
    db: SessionDep,
    current_user: CurrentUser,
    background_tasks: BackgroundTasks,
    date: str | None = Query(default=None),
):
    device = get_owned_device(db, current_user, device_id)
    date_value = _parse_date(date, _today())
    return dashboard_service.get_dashboard(db, device, date_value, background_tasks)
