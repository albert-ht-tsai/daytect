from fastapi import APIRouter, Query

from src.core.deps import CurrentUser, SessionDep
from src.dashboard.schemas.dashboard_schema import DashboardResponse
from src.dashboard.services import dashboard_service
from src.user_device.services.device_service import get_owned_device

router = APIRouter(tags=["dashboard"])


@router.get("/dashboard", response_model=DashboardResponse)
def get_dashboard_endpoint(
    db: SessionDep,
    current_user: CurrentUser,
    device_id: int = Query(...),
):
    device = get_owned_device(db, current_user, device_id)
    return dashboard_service.get_dashboard(db, device)
