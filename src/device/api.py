from fastapi import APIRouter, HTTPException

from src.core.deps import SessionDep
from src.device.schemas.activity_schema import ActivityUploadRequest
from src.device.schemas.device_schema import DeviceCreateRequest
from src.device.schemas.health_schema import HealthUploadRequest
from src.device.schemas.sleep_schema import SleepUploadRequest
from src.device.services import activity_service, device_service, health_service, sleep_service

router = APIRouter(tags=["device"])


@router.post("/device")
def create_device_endpoint(body: DeviceCreateRequest, db: SessionDep):
    device_service.create_device(db, body)
    return {"success": True, "message": "Device data saved successfully"}


@router.get("/device/{macAddress}")
def get_device_endpoint(macAddress: str, db: SessionDep):
    data = device_service.get_device_by_mac(db, macAddress)
    if data is None:
        raise HTTPException(status_code=404, detail={"code": 404, "message": "Device not found"})
    return {"success": True, "id": data.id, "name": data.name, "macAddress": data.macAddress}


@router.post("/device/{id}/sleep")
def upload_sleep_endpoint(id: int, body: SleepUploadRequest, db: SessionDep):
    sleep_service.upload_sleep(db, id, body)
    return {"success": True, "message": "Sleep record uploaded successfully"}


@router.get("/device/{id}/sleep")
def get_sleep_endpoint(id: int, date: str, db: SessionDep):
    data = sleep_service.get_sleep(db, id, date)
    if data is None:
        raise HTTPException(status_code=404, detail={"code": 404, "message": "Sleep record not found"})
    return {"success": True, **data.model_dump()}


@router.post("/device/{id}/activity")
def upload_activity_endpoint(id: int, body: ActivityUploadRequest, db: SessionDep):
    activity_service.upload_activity(db, id, body)
    return {"success": True, "message": "Activity record uploaded successfully"}


@router.get("/device/{id}/activity")
def get_activity_endpoint(id: int, date: str, db: SessionDep):
    data = activity_service.get_activity(db, id, date)
    if data is None:
        raise HTTPException(status_code=404, detail={"code": 404, "message": "Activity record not found"})
    return {"success": True, **data.model_dump()}


@router.post("/device/{id}/health")
def upload_health_endpoint(id: int, body: HealthUploadRequest, db: SessionDep):
    health_service.upload_health(db, id, body)
    return {"success": True, "message": "Health data uploaded successfully"}


@router.get("/device/{id}/health")
def get_health_endpoint(id: int, date: str, db: SessionDep):
    data = health_service.get_health(db, id, date)
    if data is None:
        raise HTTPException(status_code=404, detail={"code": 404, "message": "Health record not found"})
    return {"success": True, **data.model_dump()}
