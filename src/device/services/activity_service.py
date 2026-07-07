from sqlalchemy.orm import Session

from src.device.models.activity_model import ActivityRecord
from src.device.models.device_model import DeviceRecord
from src.device.schemas.activity_schema import ActivityUploadRequest


def upload_activity(db: Session, body: ActivityUploadRequest) -> DeviceRecord:
    """Finds the device by macAddress, creating it on the fly if it hasn't been
    registered yet (e.g. via POST /device), so activity data can always be saved."""
    device = db.query(DeviceRecord).filter(DeviceRecord.mac_address == body.macAddress).first()
    if device is None:
        device = DeviceRecord(mac_address=body.macAddress)
        db.add(device)
        db.flush()

    existing = db.query(ActivityRecord).filter(
        ActivityRecord.device_id == device.id,
        ActivityRecord.date == body.date,
    ).first()

    data = body.activityAvgRecord.model_dump()

    if existing is None:
        db.add(ActivityRecord(device_id=device.id, date=body.date, data=data))
    else:
        existing.data = data
    db.commit()
    return device
