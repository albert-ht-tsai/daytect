from pydantic import BaseModel


class DeviceCreateRequest(BaseModel):
    name: str
    macAddress: str


class DeviceResponse(BaseModel):
    id: int
    name: str | None
    macAddress: str
