from sqlalchemy.orm import Session

from src.device.models.device_model import DeviceRecord
from src.device.models.health_model import HealthRecord
from src.device.schemas.health_schema import HealthUploadRequest


def upload_health(db: Session, body: HealthUploadRequest) -> DeviceRecord | None:
    device = db.query(DeviceRecord).filter(DeviceRecord.mac_address == body.macAddress).first()
    if device is None:
        return None

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
