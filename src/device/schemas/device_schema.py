from typing import Optional

from pydantic import BaseModel


# ── POST /devices/bind ──────────────────────────────────────────────────────

class AddDeviceRequest(BaseModel):
    user_id: int
    mac_address: str
    name: Optional[str] = None
    avatar: Optional[str] = None
    group: str


class AddDeviceData(BaseModel):
    id: int
    user_id: int
    mac_address: str
    name: Optional[str] = None
    group: str
    is_share: bool
    qrcode: str
    battery: float

    model_config = {"from_attributes": True}


class AddDeviceResponse(BaseModel):
    success: bool = True
    data: AddDeviceData
    message: str = "Device added successfully."


# ── GET /devices/bind ────────────────────────────────────────────────────────

class DeviceGroupItem(BaseModel):
    id: int
    mac_address: str
    name: Optional[str] = None
    group: str
    battery: float
    is_share: bool
    qrcode: str
    avatar: Optional[str] = None

    model_config = {"from_attributes": True}


class DeviceGroupsResponse(BaseModel):
    success: bool = True
    data: dict[str, list[DeviceGroupItem]]
    message: str = "All device groups retrieved successfully."


# ── PUT /devices/bind/{device_id} ───────────────────────────────────────────

class UpdateDeviceRequest(BaseModel):
    name: Optional[str] = None
    is_share: Optional[bool] = None
    avatar: Optional[str] = None
    battery: Optional[float] = None


class UpdateDeviceResponse(BaseModel):
    success: bool = True
    data: None = None
    message: str = "Device updated successfully."


# ── DELETE /devices/bind/{device_id} ────────────────────────────────────────

class DeleteDeviceResponse(BaseModel):
    success: bool = True
    data: None = None
    message: str = "Device deleted successfully."
