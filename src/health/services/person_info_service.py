from sqlalchemy.orm import Session

from src.device.models.device_model import DeviceRecord
from src.health.models.person_info_model import PersonInfoRecord
from src.health.schemas.person_info_schema import PersonInfoUploadRequest


def upload_person_info(db: Session, body: PersonInfoUploadRequest) -> DeviceRecord:
    """Finds the device by macAddress, creating it on the fly if it hasn't been
    registered yet (e.g. via POST /device), so person-info can always be saved."""
    device = db.query(DeviceRecord).filter(DeviceRecord.mac_address == body.macAddress).first()
    if device is None:
        device = DeviceRecord(mac_address=body.macAddress)
        db.add(device)
        db.flush()

    existing = db.query(PersonInfoRecord).filter(PersonInfoRecord.device_id == device.id).first()

    if existing is None:
        db.add(
            PersonInfoRecord(
                device_id=device.id,
                mac_address=body.macAddress,
                sex=body.sex,
                age=body.age,
                height=body.height,
                weight=body.weight,
                allergy=body.allergy,
                medical_history=body.medical_history,
            )
        )
    else:
        existing.mac_address = body.macAddress
        existing.sex = body.sex
        existing.age = body.age
        existing.height = body.height
        existing.weight = body.weight
        existing.allergy = body.allergy
        existing.medical_history = body.medical_history
    db.commit()
    return device
