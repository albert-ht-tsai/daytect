from datetime import datetime
from typing import Optional

from pydantic import BaseModel


# ── Register Device ──────────────────────────────────────────────────────────

class RegisterDeviceRequest(BaseModel):
    user_id: Optional[int] = None
    mac_address: str
    name: str
    device_type: str = "wearable"
    group: str = "my_devices"


# ── Device Detail ────────────────────────────────────────────────────────────

class DeviceData(BaseModel):
    id: int
    user_id: int
    mac_address: str
    name: str
    device_type: str
    group: str
    bluetooth_status: str
    sync_status: str
    battery: Optional[int] = None
    last_sync_at: Optional[datetime] = None
    is_share: bool
    avatar: Optional[str] = None
    qrcode: str
    illustration_key: str

    model_config = {"from_attributes": True}


class DeviceDetailResponse(BaseModel):
    success: bool = True
    data: DeviceData
    message: str = "Device detail retrieved successfully."


# ── Device Groups ────────────────────────────────────────────────────────────

class DeviceSummary(BaseModel):
    id: int
    name: str
    battery: Optional[int] = None
    avatar: Optional[str] = None

    model_config = {"from_attributes": True}


class DeviceGroupsData(BaseModel):
    my_devices: list[DeviceSummary]
    family_devices: list[DeviceSummary]


class DeviceGroupsResponse(BaseModel):
    success: bool = True
    data: DeviceGroupsData
    message: str = "Device groups retrieved successfully."


# ── Update Device ────────────────────────────────────────────────────────────

class UpdateDeviceRequest(BaseModel):
    name: Optional[str] = None
    avatar: Optional[str] = None
    is_share: Optional[bool] = None


class UpdateDeviceResponse(BaseModel):
    success: bool = True
    data: None = None
    message: str = "Device updated successfully."


# ── Delete Device ────────────────────────────────────────────────────────────

class DeleteDeviceResponse(BaseModel):
    success: bool = True
    data: None = None
    message: str = "Device deleted successfully."
