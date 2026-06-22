from typing import Optional

from pydantic import BaseModel


# ── Register Device ──────────────────────────────────────────────────────────

class RegisterDeviceRequest(BaseModel):
    user_id: Optional[int] = None
    mac_address: str
    name: str
    group: str = "my_devices"


# ── Device Detail ────────────────────────────────────────────────────────────

class DeviceData(BaseModel):
    id: int
    user_id: int
    mac_address: str
    name: str
    group: str
    battery: Optional[int] = None
    is_share: bool
    qrcode: str
    avatar: Optional[str] = None

    model_config = {"from_attributes": True}


class DeviceDetailResponse(BaseModel):
    success: bool = True
    data: DeviceData
    message: str = "Device detail retrieved successfully."


# ── Device Groups ────────────────────────────────────────────────────────────

class DeviceSummary(BaseModel):
    id: int
    mac_address: str
    name: str
    group: str
    battery: Optional[int] = None
    is_share: bool
    qrcode: str
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
    is_share: Optional[bool] = None


class UpdateDeviceResponse(BaseModel):
    success: bool = True
    data: None = None
    message: str = "Device updated successfully."


# ── Device Avatar ────────────────────────────────────────────────────────────

class DeviceAvatarData(BaseModel):
    avatar: str


class DeviceAvatarResponse(BaseModel):
    success: bool = True
    data: DeviceAvatarData
    message: str = "Device avatar updated successfully."


# ── Delete Device ────────────────────────────────────────────────────────────

class DeleteDeviceResponse(BaseModel):
    success: bool = True
    data: None = None
    message: str = "Device deleted successfully."
