from fastapi import HTTPException, UploadFile, status
from sqlalchemy.orm import Session

from src.core.config import BASE_URL
from src.core.files import save_avatar
from src.user.models.user_model import User
from src.user_device.models.device_model import Device
from src.user_device.schemas.device_schema import (
    DeviceAvatarData,
    DeviceAvatarResponse,
    DeviceData,
    DeviceDetailResponse,
    DeviceGroupsData,
    DeviceGroupsResponse,
    DeviceSummary,
    RegisterDeviceRequest,
    UpdateDeviceRequest,
)


def _to_data(device: Device) -> DeviceData:
    return DeviceData.model_validate(device)


def register_device(db: Session, user: User, body: RegisterDeviceRequest) -> DeviceDetailResponse:
    if body.user_id is not None and body.user_id != user.id:
        raise HTTPException(
            status.HTTP_403_FORBIDDEN,
            detail={"code": 403, "message": "Cannot register a device for another user"},
        )

    if db.query(Device).filter(Device.mac_address == body.mac_address).first():
        raise HTTPException(
            status.HTTP_400_BAD_REQUEST,
            detail={"code": 400, "message": "Device with this MAC address already registered"},
        )

    device = Device(
        user_id=user.id,
        mac_address=body.mac_address,
        name=body.name,
        group=body.group,
        qrcode=f"{BASE_URL}/qrcode/{body.mac_address}",
    )
    db.add(device)
    db.commit()
    db.refresh(device)
    return DeviceDetailResponse(data=_to_data(device), message="Device registered successfully.")


def get_owned_device(db: Session, user: User, device_id: int) -> Device:
    device = db.query(Device).filter(Device.id == device_id, Device.user_id == user.id).first()
    if not device:
        raise HTTPException(
            status.HTTP_404_NOT_FOUND,
            detail={"code": 404, "message": "Device not found"},
        )
    return device


def get_device_detail(db: Session, user: User, device_id: int) -> DeviceDetailResponse:
    device = get_owned_device(db, user, device_id)
    return DeviceDetailResponse(data=_to_data(device))


def list_device_groups(db: Session, user: User, target_user_id: int) -> DeviceGroupsResponse:
    if target_user_id != user.id:
        raise HTTPException(
            status.HTTP_403_FORBIDDEN,
            detail={"code": 403, "message": "Not authorized to view this user's devices"},
        )

    devices = db.query(Device).filter(Device.user_id == user.id).all()
    my_devices = [d for d in devices if d.group != "family_devices"]
    family_devices = [d for d in devices if d.group == "family_devices"]
    return DeviceGroupsResponse(
        data=DeviceGroupsData(
            my_devices=[DeviceSummary.model_validate(d) for d in my_devices],
            family_devices=[DeviceSummary.model_validate(d) for d in family_devices],
        )
    )


def update_device(db: Session, user: User, device_id: int, body: UpdateDeviceRequest) -> None:
    device = get_owned_device(db, user, device_id)
    for field, value in body.model_dump(exclude_unset=True).items():
        setattr(device, field, value)
    db.add(device)
    db.commit()


def update_device_avatar(db: Session, user: User, device_id: int, file: UploadFile) -> DeviceAvatarResponse:
    device = get_owned_device(db, user, device_id)
    device.avatar = save_avatar(file, "device", device.id)
    db.add(device)
    db.commit()
    return DeviceAvatarResponse(data=DeviceAvatarData(avatar=device.avatar))


def delete_device(db: Session, user: User, device_id: int) -> None:
    device = get_owned_device(db, user, device_id)
    db.delete(device)
    db.commit()
