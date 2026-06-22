from fastapi import APIRouter, File, UploadFile

from src.core.deps import CurrentUser, SessionDep
from src.user_device.schemas.device_schema import (
    DeleteDeviceResponse,
    DeviceAvatarResponse,
    DeviceDetailResponse,
    DeviceGroupsResponse,
    RegisterDeviceRequest,
    UpdateDeviceRequest,
    UpdateDeviceResponse,
)
from src.user_device.services.device_service import (
    delete_device,
    get_device_detail,
    list_device_groups,
    register_device,
    update_device,
    update_device_avatar,
)

router = APIRouter(tags=["devices"])


@router.post("/devices", response_model=DeviceDetailResponse, status_code=201)
def register_device_endpoint(body: RegisterDeviceRequest, db: SessionDep, current_user: CurrentUser):
    return register_device(db, current_user, body)


@router.get("/devices/{device_id}", response_model=DeviceDetailResponse)
def get_device_endpoint(device_id: int, db: SessionDep, current_user: CurrentUser):
    return get_device_detail(db, current_user, device_id)


@router.get("/users/{user_id}/devices", response_model=DeviceGroupsResponse)
def get_user_device_groups_endpoint(user_id: int, db: SessionDep, current_user: CurrentUser):
    return list_device_groups(db, current_user, user_id)


@router.put("/devices/{device_id}", response_model=UpdateDeviceResponse)
def update_device_endpoint(device_id: int, body: UpdateDeviceRequest, db: SessionDep, current_user: CurrentUser):
    update_device(db, current_user, device_id, body)
    return UpdateDeviceResponse()


@router.post("/devices/{device_id}/avatar", response_model=DeviceAvatarResponse)
def update_device_avatar_endpoint(
    device_id: int, db: SessionDep, current_user: CurrentUser, file: UploadFile = File(...)
):
    return update_device_avatar(db, current_user, device_id, file)


@router.delete("/devices/{device_id}", response_model=DeleteDeviceResponse)
def delete_device_endpoint(device_id: int, db: SessionDep, current_user: CurrentUser):
    delete_device(db, current_user, device_id)
    return DeleteDeviceResponse()
