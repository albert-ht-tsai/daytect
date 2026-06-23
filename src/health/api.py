from fastapi import APIRouter

from src.core.deps import CurrentUser, SessionDep
from src.health.schemas.health_schema import (
    UploadHealthOriginRequest,
    UploadSleepRequest,
)
from src.health.services import health_service
from src.user_device.services.device_service import get_owned_device

router = APIRouter(tags=["health"])


@router.post("/health/{device_id}/health-origin", status_code=201)
def upload_health_origin_endpoint(
    device_id: int, body: UploadHealthOriginRequest, db: SessionDep, current_user: CurrentUser
):
    device = get_owned_device(db, current_user, device_id)
    health_service.upload_health_origin_data(db, device, body)
    return {
        "success": True,
        "message": "Health origin data uploaded successfully.",
    }


@router.post("/health/{device_id}/sleep", status_code=201)
def upload_sleep_endpoint(
    device_id: int, body: UploadSleepRequest, db: SessionDep, current_user: CurrentUser
):
    device = get_owned_device(db, current_user, device_id)
    health_service.upload_sleep_data(db, device, body)
    return {
        "success": True,
        "message": "Sleep data uploaded successfully.",
    }
