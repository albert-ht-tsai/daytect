from fastapi import APIRouter, BackgroundTasks, Query
from pydantic import BaseModel

from src.core.deps import CurrentUser, SessionDep
from src.device.services.device_service import get_device_by_mac
from src.health.schemas.health_schema import UploadHealthRequest
from src.health.services import health_service
from src.health.services import health_summary_service

router = APIRouter(tags=["health"])


@router.post("/health/upload", status_code=201)
def upload_health_endpoint(body: UploadHealthRequest, db: SessionDep, current_user: CurrentUser):
    device = get_device_by_mac(db, current_user, body.mac_address)
    health_service.upload_health(db, device, body)
    return {"success": True, "message": "Health data uploaded successfully."}


class _SummaryRequestBody(BaseModel):
    date: str


@router.post("/health/summary/request", status_code=202)
def request_health_summary_endpoint(
    body: _SummaryRequestBody,
    db: SessionDep,
    current_user: CurrentUser,
    background_tasks: BackgroundTasks,
):
    data = health_summary_service.request_summary(db, current_user.id, body.date, background_tasks)
    return {"success": True, "data": data, "message": "AI health summary job created."}


@router.get("/health/summary/progress")
def get_health_summary_progress_endpoint(
    db: SessionDep,
    current_user: CurrentUser,
    job_id: str = Query(...),
):
    data = health_summary_service.get_progress(db, current_user.id, job_id)
    return {"success": True, "data": data, "message": "AI health summary progress retrieved."}


@router.get("/health/summary/result")
def get_health_summary_result_endpoint(
    db: SessionDep,
    current_user: CurrentUser,
    job_id: str = Query(...),
):
    data = health_summary_service.get_result(db, current_user.id, job_id)
    return {"success": True, "data": data, "message": "AI health summary retrieved."}
