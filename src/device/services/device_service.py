from sqlalchemy.orm import Session

from src.device.models.device_model import DeviceRecord
from src.device.schemas.device_schema import DeviceCreateRequest, DeviceResponse


def create_device(db: Session, body: DeviceCreateRequest, user_id: int | None = None) -> None:
    """user_id is set opportunistically when the caller is logged in (see POST /device), binding
    this device so health-report generation can later resolve "the caller's device" by user_id
    instead of macAddress. An unauthenticated call still works and leaves user_id untouched."""
    existing = db.query(DeviceRecord).filter(DeviceRecord.mac_address == body.macAddress).first()
    if existing is None:
        db.add(
            DeviceRecord(
                name=body.name,
                mac_address=body.macAddress,
                user_id=user_id,
                battery=body.battery,
                last_sync=body.lastSync,
                is_connected=body.isConnected,
            )
        )
    else:
        existing.name = body.name
        existing.battery = body.battery
        existing.last_sync = body.lastSync
        existing.is_connected = body.isConnected
        if user_id is not None:
            existing.user_id = user_id
    db.commit()


def get_device_by_mac(db: Session, mac_address: str) -> DeviceResponse | None:
    record = db.query(DeviceRecord).filter(DeviceRecord.mac_address == mac_address).first()
    if record is None:
        return None
    return DeviceResponse(
        id=record.id,
        name=record.name,
        macAddress=record.mac_address,
        userId=record.user_id,
        battery=record.battery,
        lastSync=record.last_sync,
        isConnected=record.is_connected,
    )
