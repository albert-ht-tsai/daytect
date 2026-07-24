from sqlalchemy.orm import Session

from src.device.models.device_model import DeviceRecord
from src.device.models.health_model import HealthRecord
from src.device.schemas.health_schema import HealthDataResponse, HealthUploadRequest


def upload_health(db: Session, body: HealthUploadRequest, user_id: int | None = None) -> DeviceRecord:
    """Finds the device by macAddress, creating it on the fly if it hasn't been
    registered yet (e.g. via POST /device), so health data can always be saved.

    user_id is set opportunistically when the caller is logged in — mirrors
    device_service.create_device, since a sync call can be the first time this device is ever
    seen by the backend (the client doesn't necessarily call POST /device before syncing)."""
    device = db.query(DeviceRecord).filter(DeviceRecord.mac_address == body.macAddress).first()
    if device is None:
        device = DeviceRecord(mac_address=body.macAddress, user_id=user_id)
        db.add(device)
        db.flush()
    elif user_id is not None:
        device.user_id = user_id

    existing = db.query(HealthRecord).filter(
        HealthRecord.device_id == device.id,
        HealthRecord.date == body.date,
    ).first()

    data = body.healthAvgRecord.model_dump()

    if existing is None:
        db.add(HealthRecord(device_id=device.id, date=body.date, data=data))
    else:
        existing.data = data
    db.commit()
    return device


def get_health(db: Session, mac_address: str, date: str) -> HealthDataResponse | None:
    device = db.query(DeviceRecord).filter(DeviceRecord.mac_address == mac_address).first()
    if device is None:
        return None

    record = db.query(HealthRecord).filter(
        HealthRecord.device_id == device.id,
        HealthRecord.date == date,
    ).first()
    if record is None:
        return None

    return HealthDataResponse(
        id=record.id,
        macAddress=mac_address,
        date=record.date,
        healthAvgRecord=record.data,
    )
