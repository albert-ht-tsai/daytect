import secrets

from fastapi import HTTPException, status
from sqlalchemy.orm import Session

from src.device.models.device_model import Device
from src.device.schemas.device_schema import (
    AddDeviceData,
    AddDeviceRequest,
    AddDeviceResponse,
    DeviceGroupItem,
    DeviceGroupsResponse,
    UpdateDeviceRequest,
)
from src.profile.models.user_model import User

_DEFAULT_GROUPS = ["my_devices", "family_devices"]


def get_owned_device(db: Session, user: User, device_id: int) -> Device:
    device = db.query(Device).filter(Device.id == device_id, Device.user_id == user.id).first()
    if not device:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail={"code": 404, "message": "Device not found"})
    return device


def get_device_by_mac(db: Session, user: User, mac_address: str) -> Device:
    device = db.query(Device).filter(Device.mac_address == mac_address, Device.user_id == user.id).first()
    if not device:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail={"code": 404, "message": "Device not found"})
    return device


# ── POST /devices/bind ──────────────────────────────────────────────────────

def add_device(db: Session, user: User, data: AddDeviceRequest) -> AddDeviceResponse:
    # Owner is always the authenticated user, never data.user_id — trusting a client-supplied
    # user_id would let one account bind devices onto another account's device list.
    device = Device(
        user_id=user.id,
        mac_address=data.mac_address,
        name=data.name,
        avatar=data.avatar,
        group=data.group,
        qrcode=secrets.token_hex(8),
    )
    db.add(device)
    db.commit()
    db.refresh(device)
    return AddDeviceResponse(data=AddDeviceData.model_validate(device))


# ── GET /devices/bind ────────────────────────────────────────────────────────

def get_device_groups(db: Session, user: User) -> DeviceGroupsResponse:
    devices = db.query(Device).filter(Device.user_id == user.id).all()
    groups: dict[str, list[DeviceGroupItem]] = {group: [] for group in _DEFAULT_GROUPS}
    for device in devices:
        groups.setdefault(device.group, []).append(DeviceGroupItem.model_validate(device))
    return DeviceGroupsResponse(data=groups)


# ── PUT /devices/bind/{device_id} ───────────────────────────────────────────

def update_device(db: Session, user: User, device_id: int, data: UpdateDeviceRequest) -> Device:
    device = get_owned_device(db, user, device_id)
    for field, value in data.model_dump(exclude_unset=True).items():
        setattr(device, field, value)
    db.add(device)
    db.commit()
    return device


# ── DELETE /devices/bind/{device_id} ────────────────────────────────────────

def delete_device(db: Session, user: User, device_id: int) -> None:
    device = get_owned_device(db, user, device_id)
    db.delete(device)
    db.commit()
