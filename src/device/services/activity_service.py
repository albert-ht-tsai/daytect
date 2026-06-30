from sqlalchemy.orm import Session

from src.device.models.activity_model import ActivityRecord
from src.device.schemas.activity_schema import ActivityEntry, ActivityResponse, ActivityUploadRequest


def upload_activity(db: Session, device_id: int, body: ActivityUploadRequest) -> None:
    existing = db.query(ActivityRecord).filter(
        ActivityRecord.device_id == device_id,
        ActivityRecord.date == body.date,
    ).first()

    data = [entry.model_dump() for entry in body.data]

    if existing is None:
        db.add(ActivityRecord(device_id=device_id, date=body.date, data=data))
    else:
        existing.data = data
    db.commit()


def get_activity(db: Session, device_id: int, date: str) -> ActivityResponse | None:
    record = db.query(ActivityRecord).filter(
        ActivityRecord.device_id == device_id,
        ActivityRecord.date == date,
    ).first()
    if record is None:
        return None

    entries = [ActivityEntry(**entry) for entry in (record.data or [])]
    return ActivityResponse(date=record.date, data=entries)
