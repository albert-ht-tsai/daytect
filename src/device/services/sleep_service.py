from sqlalchemy.orm import Session

from src.device.models.sleep_model import SleepRecord
from src.device.schemas.sleep_schema import SleepUploadRequest, SleepResponse, TimePoint


def upload_sleep(db: Session, device_id: int, body: SleepUploadRequest) -> None:
    existing = db.query(SleepRecord).filter(
        SleepRecord.device_id == device_id,
        SleepRecord.date == body.date,
    ).first()

    fields = {
        "sleep_quality": body.sleepQuality,
        "wake_count": body.wakeCount,
        "deep_sleep_time": body.deepSleepTime,
        "low_sleep_time": body.lowSleepTime,
        "all_sleep_time": body.allSleepTime,
        "sleep_line": body.sleepLine,
        "sleep_down_hour": body.sleepDown.hour if body.sleepDown else None,
        "sleep_down_minute": body.sleepDown.minute if body.sleepDown else None,
        "sleep_up_hour": body.sleepUp.hour if body.sleepUp else None,
        "sleep_up_minute": body.sleepUp.minute if body.sleepUp else None,
    }

    if existing is None:
        db.add(SleepRecord(device_id=device_id, date=body.date, **fields))
    else:
        for attr, val in fields.items():
            if val is not None:
                setattr(existing, attr, val)
    db.commit()


def get_sleep(db: Session, device_id: int, date: str) -> SleepResponse | None:
    record = db.query(SleepRecord).filter(
        SleepRecord.device_id == device_id,
        SleepRecord.date == date,
    ).first()
    if record is None:
        return None

    sleep_down = (
        TimePoint(hour=record.sleep_down_hour, minute=record.sleep_down_minute)
        if record.sleep_down_hour is not None
        else None
    )
    sleep_up = (
        TimePoint(hour=record.sleep_up_hour, minute=record.sleep_up_minute)
        if record.sleep_up_hour is not None
        else None
    )

    return SleepResponse(
        date=record.date,
        sleepQuality=record.sleep_quality,
        wakeCount=record.wake_count,
        deepSleepTime=record.deep_sleep_time,
        lowSleepTime=record.low_sleep_time,
        allSleepTime=record.all_sleep_time,
        sleepLine=record.sleep_line,
        sleepDown=sleep_down,
        sleepUp=sleep_up,
    )
