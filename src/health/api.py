from fastapi import APIRouter

from src.core.deps import CurrentUser, SessionDep
from src.health.schemas.health_schema import UploadDailyHealthRequest
from src.health.services import health_service
from src.user_device.services.device_service import get_owned_device

router = APIRouter(tags=["health"])


@router.post("/health/{device_id}/daily-health", status_code=201)
def upload_daily_health_endpoint(
    device_id: int, body: UploadDailyHealthRequest, db: SessionDep, current_user: CurrentUser
):
    device = get_owned_device(db, current_user, device_id)
    health_service.upload_daily_health(db, device, body)
    return {
        "success": True,
        "message": "Daily health data uploaded successfully.",
    }
