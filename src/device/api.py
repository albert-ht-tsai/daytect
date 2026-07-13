from fastapi import APIRouter, HTTPException

from src.core.deps import SessionDep
from src.device.schemas.activity_schema import ActivityUploadRequest
from src.device.schemas.device_schema import DeviceCreateRequest
from src.device.schemas.health_schema import HealthDataResponse, HealthUploadRequest
from src.device.schemas.sleep_schema import SleepDataResponse, SleepUploadRequest
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
    return {"success": True, "data": data}


@router.post("/device/sleep")
def upload_sleep_endpoint(body: SleepUploadRequest, db: SessionDep):
    sleep_service.upload_sleep(db, body)
    return {"success": True, "message": "Sleep data saved successfully"}


@router.get("/device/sleep/{macAddress}", response_model=SleepDataResponse)
def get_sleep_endpoint(macAddress: str, date: str, db: SessionDep):
    result = sleep_service.get_sleep(db, macAddress, date)
    if result is None:
        raise HTTPException(status_code=404, detail={"code": 404, "message": "Sleep data not found"})
    return result


@router.post("/device/activity")
def upload_activity_endpoint(body: ActivityUploadRequest, db: SessionDep):
    activity_service.upload_activity(db, body)
    return {"success": True, "message": "Activity data saved successfully"}


@router.post("/device/health")
def upload_health_endpoint(body: HealthUploadRequest, db: SessionDep):
    health_service.upload_health(db, body)
    return {"success": True, "message": "Health data saved successfully"}


@router.get("/device/health/{macAddress}", response_model=HealthDataResponse)
def get_health_endpoint(macAddress: str, date: str, db: SessionDep):
    result = health_service.get_health(db, macAddress, date)
    if result is None:
        raise HTTPException(status_code=404, detail={"code": 404, "message": "Health data not found"})
    return result
