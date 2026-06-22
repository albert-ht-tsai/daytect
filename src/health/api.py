from datetime import date as date_cls
from datetime import datetime, timezone

from fastapi import APIRouter, HTTPException, Query, status

from src.core.deps import CurrentUser, SessionDep
from src.health.schemas.health_schema import (
    AvailableDatesResponse,
    HealthDataByDateResponse,
    UploadHealthDataResponseData,
    UploadHealthOriginRequest,
    UploadHealthOriginResponseData,
    UploadSleepRequest,
)
from src.health.services import health_service
from src.user_device.services.device_service import get_owned_device

router = APIRouter(tags=["health"])


def _today() -> date_cls:
    return datetime.now(timezone.utc).date()


def _parse_date(value: str | None, default: date_cls) -> date_cls:
    if value is None:
        return default
    try:
        return date_cls.fromisoformat(value)
    except ValueError:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, detail={"code": 400, "message": "Invalid date format"})


@router.post("/health/{device_id}/health-origin", status_code=201)
def upload_health_origin_endpoint(
    device_id: int, body: UploadHealthOriginRequest, db: SessionDep, current_user: CurrentUser
):
    device = get_owned_device(db, current_user, device_id)
    record_ids = health_service.upload_health_origin_data(db, device, body)
    return {
        "success": True,
        "data": UploadHealthOriginResponseData(record_ids=record_ids),
        "message": "Health origin data uploaded successfully.",
    }


@router.post("/health/{device_id}/sleep", status_code=201)
def upload_sleep_endpoint(
    device_id: int, body: UploadSleepRequest, db: SessionDep, current_user: CurrentUser
):
    device = get_owned_device(db, current_user, device_id)
    record_id = health_service.upload_sleep_data(db, device, body)
    return {
        "success": True,
        "data": UploadHealthDataResponseData(health_record_id=str(record_id)),
        "message": "Sleep data uploaded successfully.",
    }


@router.get("/health/{device_id}/dates", response_model=AvailableDatesResponse)
def get_health_dates_endpoint(device_id: int, db: SessionDep, current_user: CurrentUser):
    device = get_owned_device(db, current_user, device_id)
    return AvailableDatesResponse(dates=health_service.get_available_dates(db, device))


@router.get("/health/{device_id}", response_model=HealthDataByDateResponse)
def get_health_data_endpoint(
    device_id: int, db: SessionDep, current_user: CurrentUser, date: str | None = Query(default=None)
):
    device = get_owned_device(db, current_user, device_id)
    date_value = _parse_date(date, _today())
    result = health_service.get_health_data_by_date(db, device, date_value)
    if result is None:
        raise HTTPException(
            status.HTTP_404_NOT_FOUND, detail={"code": 404, "message": "No health data found for this date"}
        )
    return result
