from sqlalchemy.orm import Session

from src.device.models.device_model import DeviceRecord
from src.health.models.person_info_model import PersonInfoRecord
from src.health.schemas.person_info_schema import PersonInfoUploadRequest


def upload_person_info(db: Session, mac_address: str, body: PersonInfoUploadRequest) -> DeviceRecord | None:
    device = db.query(DeviceRecord).filter(DeviceRecord.mac_address == mac_address).first()
    if device is None:
        return None

    existing = db.query(PersonInfoRecord).filter(PersonInfoRecord.device_id == device.id).first()

    if existing is None:
        db.add(
            PersonInfoRecord(
                device_id=device.id,
                sex=body.sex,
                age=body.age,
                height=body.height,
                weight=body.weight,
                allergy=body.allergy,
                medical_history=body.medical_history,
            )
        )
    else:
        existing.sex = body.sex
        existing.age = body.age
        existing.height = body.height
        existing.weight = body.weight
        existing.allergy = body.allergy
        existing.medical_history = body.medical_history
    db.commit()
    return device
