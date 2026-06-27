from fastapi import APIRouter, BackgroundTasks, Query
from pydantic import BaseModel

from src.core.deps import CurrentUser, SessionDep
from src.device.services.device_service import get_owned_device
from src.health.schemas.health_schema import UploadHealthRequest
from src.health.services import health_service
from src.health.services import health_summary_service

router = APIRouter(tags=["health"])


@router.post("/health/{device_id}/upload", status_code=201)
def upload_health_endpoint(device_id: int, body: UploadHealthRequest, db: SessionDep, current_user: CurrentUser):
    device = get_owned_device(db, current_user, device_id)
    health_service.upload_health(db, device, body)
    return {"success": True, "message": "Health data uploaded successfully."}


class _SummaryRequestBody(BaseModel):
    date: str


@router.post("/health/{device_id}/summary/request", status_code=202)
def request_health_summary_endpoint(
    device_id: int,
    body: _SummaryRequestBody,
    db: SessionDep,
    current_user: CurrentUser,
    background_tasks: BackgroundTasks,
):
    device = get_owned_device(db, current_user, device_id)
    data = health_summary_service.request_summary(db, device, body.date, background_tasks)
    return {"success": True, "data": data, "message": "AI health summary job created."}


@router.get("/health/{device_id}/summary/progress")
def get_health_summary_progress_endpoint(
    device_id: int,
    db: SessionDep,
    current_user: CurrentUser,
    job_id: str = Query(...),
):
    device = get_owned_device(db, current_user, device_id)
    data = health_summary_service.get_progress(db, device, job_id)
    return {"success": True, "data": data, "message": "AI health summary progress retrieved."}


@router.get("/health/{device_id}/summary/result")
def get_health_summary_result_endpoint(
    device_id: int,
    db: SessionDep,
    current_user: CurrentUser,
    job_id: str = Query(...),
):
    device = get_owned_device(db, current_user, device_id)
    data = health_summary_service.get_result(db, device, job_id)
    return {"success": True, "data": data, "message": "AI health summary retrieved."}
