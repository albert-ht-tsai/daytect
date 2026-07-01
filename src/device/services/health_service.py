from sqlalchemy.orm import Session

from src.device.models.device_model import DeviceRecord
from src.device.models.health_model import HealthRecord
from src.device.schemas.health_schema import HealthUploadRequest


def upload_health(db: Session, body: HealthUploadRequest) -> DeviceRecord | None:
    device = db.query(DeviceRecord).filter(DeviceRecord.mac_address == body.macAddress).first()
    if device is None:
        return None

    record = body.healthRecord
    existing = db.query(HealthRecord).filter(
        HealthRecord.device_id == device.id,
        HealthRecord.entry_datetime == record.datetime,
    ).first()

    data = record.model_dump()

    if existing is None:
        db.add(HealthRecord(device_id=device.id, entry_datetime=record.datetime, data=data))
    else:
        existing.data = data
    db.commit()
    return device
