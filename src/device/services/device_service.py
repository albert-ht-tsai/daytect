from sqlalchemy.orm import Session

from src.device.models.device_model import DeviceRecord
from src.device.schemas.device_schema import DeviceCreateRequest, DeviceResponse


def create_device(db: Session, body: DeviceCreateRequest) -> None:
    existing = db.query(DeviceRecord).filter(DeviceRecord.mac_address == body.macAddress).first()
    if existing is None:
        db.add(DeviceRecord(name=body.name, mac_address=body.macAddress))
    else:
        existing.name = body.name
    db.commit()


def get_device_by_mac(db: Session, mac_address: str) -> DeviceResponse | None:
    record = db.query(DeviceRecord).filter(DeviceRecord.mac_address == mac_address).first()
    if record is None:
        return None
    return DeviceResponse(id=record.id, name=record.name, macAddress=record.mac_address)
