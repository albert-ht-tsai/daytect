from sqlalchemy.orm import Session

from src.device.models.device_model import DeviceRecord
from src.device.models.sleep_model import SleepRecord
from src.device.schemas.sleep_schema import SleepUploadRequest


def upload_sleep(db: Session, body: SleepUploadRequest) -> DeviceRecord | None:
    device = db.query(DeviceRecord).filter(DeviceRecord.mac_address == body.macAddress).first()
    if device is None:
        return None

    record = body.sleepRecord
    existing = db.query(SleepRecord).filter(
        SleepRecord.device_id == device.id,
        SleepRecord.date == record.date,
    ).first()

    fields = {
        "sleep_quality": record.sleepQuality,
        "wake_count": record.wakeCount,
        "deep_sleep_time": record.deepSleepTime,
        "low_sleep_time": record.lowSleepTime,
        "all_sleep_time": record.allSleepTime,
        "sleep_line": record.sleepLine,
        "sleep_down_hour": record.sleepDown.hour if record.sleepDown else None,
        "sleep_down_minute": record.sleepDown.minute if record.sleepDown else None,
        "sleep_up_hour": record.sleepUp.hour if record.sleepUp else None,
        "sleep_up_minute": record.sleepUp.minute if record.sleepUp else None,
    }

    if existing is None:
        db.add(SleepRecord(device_id=device.id, date=record.date, **fields))
    else:
        for attr, val in fields.items():
            setattr(existing, attr, val)
    db.commit()
    return device
