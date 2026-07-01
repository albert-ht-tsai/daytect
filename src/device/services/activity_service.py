from sqlalchemy.orm import Session

from src.device.models.activity_model import ActivityRecord
from src.device.models.device_model import DeviceRecord
from src.device.schemas.activity_schema import ActivityUploadRequest


def upload_activity(db: Session, body: ActivityUploadRequest) -> DeviceRecord | None:
    device = db.query(DeviceRecord).filter(DeviceRecord.mac_address == body.macAddress).first()
    if device is None:
        return None

    record = body.activityRecord
    existing = db.query(ActivityRecord).filter(
        ActivityRecord.device_id == device.id,
        ActivityRecord.entry_datetime == record.datetime,
    ).first()

    data = record.model_dump()

    if existing is None:
        db.add(ActivityRecord(device_id=device.id, entry_datetime=record.datetime, data=data))
    else:
        existing.data = data
    db.commit()
    return device
