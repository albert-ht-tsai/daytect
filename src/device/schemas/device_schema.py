from pydantic import BaseModel


class DeviceCreateRequest(BaseModel):
    id: int | None = None
    name: str
    macAddress: str
    battery: int | None = None
    lastSync: str | None = None
    isConnected: bool = False


class DeviceResponse(BaseModel):
    id: int
    name: str | None
    macAddress: str
    battery: int | None = None
    lastSync: str | None = None
    isConnected: bool = False
