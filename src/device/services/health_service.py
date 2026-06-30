from sqlalchemy.orm import Session

from src.device.models.health_model import HealthRecord
from src.device.schemas.health_schema import HealthEntry, HealthResponse, HealthUploadRequest


def upload_health(db: Session, device_id: int, body: HealthUploadRequest) -> None:
    existing = db.query(HealthRecord).filter(
        HealthRecord.device_id == device_id,
        HealthRecord.date == body.date,
    ).first()

    data = [entry.model_dump() for entry in body.data]

    if existing is None:
        db.add(HealthRecord(device_id=device_id, date=body.date, data=data))
    else:
        existing.data = data
    db.commit()


def get_health(db: Session, device_id: int, date: str) -> HealthResponse | None:
    record = db.query(HealthRecord).filter(
        HealthRecord.device_id == device_id,
        HealthRecord.date == date,
    ).first()
    if record is None:
        return None

    entries = [HealthEntry(**entry) for entry in (record.data or [])]
    return HealthResponse(date=record.date, data=entries)
