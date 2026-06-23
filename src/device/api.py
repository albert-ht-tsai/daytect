from fastapi import APIRouter

from src.core.deps import CurrentUser, SessionDep
from src.device.schemas.device_schema import (
    AddDeviceRequest,
    AddDeviceResponse,
    DeleteDeviceResponse,
    DeviceGroupsResponse,
    UpdateDeviceRequest,
    UpdateDeviceResponse,
)
from src.device.services.device_service import (
    add_device,
    delete_device,
    get_device_groups,
    update_device,
)

router = APIRouter(prefix="/devices", tags=["devices"])


@router.post("/bind", response_model=AddDeviceResponse, status_code=201)
def add_device_endpoint(body: AddDeviceRequest, db: SessionDep, current_user: CurrentUser):
    return add_device(db, current_user, body)


@router.get("/bind", response_model=DeviceGroupsResponse)
def get_device_groups_endpoint(db: SessionDep, current_user: CurrentUser):
    return get_device_groups(db, current_user)


@router.put("/bind/{device_id}", response_model=UpdateDeviceResponse)
def update_device_endpoint(device_id: int, body: UpdateDeviceRequest, db: SessionDep, current_user: CurrentUser):
    update_device(db, current_user, device_id, body)
    return UpdateDeviceResponse()


@router.delete("/bind/{device_id}", response_model=DeleteDeviceResponse)
def delete_device_endpoint(device_id: int, db: SessionDep, current_user: CurrentUser):
    delete_device(db, current_user, device_id)
    return DeleteDeviceResponse()
