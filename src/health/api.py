from fastapi import APIRouter, HTTPException, Query, status
from fastapi.responses import JSONResponse

from datetime import date as date_cls

from src.core.deps import CurrentUser, SessionDep
from src.device.services.device_service import get_owned_device
from src.health.schemas.health_schema import UploadHealthRequest
from src.health.services import health_service

router = APIRouter(tags=["health"])

_FULL_DAY_START = "00:00:00"
_FULL_DAY_END = "23:59:59"


def _parse_date(value: str) -> date_cls:
    try:
        return date_cls.fromisoformat(value)
    except ValueError:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, detail={"code": 400, "message": "Invalid date format"})


@router.post("/health/{device_id}/upload", status_code=201)
def upload_health_endpoint(device_id: int, body: UploadHealthRequest, db: SessionDep, current_user: CurrentUser):
    device = get_owned_device(db, current_user, device_id)
    health_service.upload_health(db, device, body)
    return {"success": True, "message": "Health data uploaded successfully."}


@router.get("/health/{device_id}/daily")
def get_daily_health_status_endpoint(
    device_id: int, db: SessionDep, current_user: CurrentUser, date: str = Query(...)
):
    device = get_owned_device(db, current_user, device_id)
    _parse_date(date)
    data = health_service.get_daily_status(db, device, date, _FULL_DAY_START, _FULL_DAY_END)
    if data is None:
        return JSONResponse(
            status_code=404,
            content={"success": False, "data": None, "message": "Daily health data not found."},
        )
    return {"success": True, "data": data, "message": "Daily health status retrieved successfully."}


@router.get("/health/{device_id}/weekly")
def get_weekly_health_status_endpoint(
    device_id: int, db: SessionDep, current_user: CurrentUser, date: str = Query(...)
):
    device = get_owned_device(db, current_user, device_id)
    _parse_date(date)
    data = health_service.get_weekly_status(db, device, date, _FULL_DAY_START, _FULL_DAY_END)
    if data is None:
        return JSONResponse(
            status_code=404,
            content={"success": False, "data": None, "message": "Weekly health data not found."},
        )
    return {"success": True, "data": data, "message": "Weekly health status retrieved successfully."}
