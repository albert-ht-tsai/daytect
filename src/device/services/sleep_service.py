from datetime import datetime

from sqlalchemy.orm import Session

from src.device.models.device_model import DeviceRecord
from src.device.models.sleep_model import SleepRecord
from src.device.schemas.sleep_schema import SleepDataResponse, SleepRecordPayload, SleepUploadRequest


def _sort_key(record: SleepRecordPayload) -> str:
    return record.startDateTime or ""


def _sum(values: list[int | None]) -> int | None:
    present = [v for v in values if v is not None]
    return sum(present) if present else None


def _weighted_avg_quality(records: list[SleepRecordPayload]) -> int | None:
    pairs = [(r.sleepQuality, r.allSleepTime) for r in records if r.sleepQuality is not None]
    if not pairs:
        return None
    if all(weight for _, weight in pairs):
        total_weight = sum(weight for _, weight in pairs)
        return round(sum(quality * weight for quality, weight in pairs) / total_weight)
    return round(sum(quality for quality, _ in pairs) / len(pairs))


def _parse_dt(value: str | None) -> datetime | None:
    if not value:
        return None
    try:
        return datetime.fromisoformat(value)
    except ValueError:
        return None


def _earliest(values: list[str | None]) -> str | None:
    parsed = [(v, _parse_dt(v)) for v in values]
    parsed = [(v, dt) for v, dt in parsed if dt is not None]
    return min(parsed, key=lambda pair: pair[1])[0] if parsed else None


def _latest(values: list[str | None]) -> str | None:
    parsed = [(v, _parse_dt(v)) for v in values]
    parsed = [(v, dt) for v, dt in parsed if dt is not None]
    return max(parsed, key=lambda pair: pair[1])[0] if parsed else None


def _merge_sleep_line(records: list[SleepRecordPayload]) -> str | None:
    lines = [r.sleepLine for r in records if r.sleepLine]
    return "".join(lines) if lines else None


def _compute_summary(records: list[SleepRecordPayload]) -> dict:
    return {
        "sleepQuality": _weighted_avg_quality(records),
        "wakeCount": _sum([r.wakeCount for r in records]),
        "deepSleepTime": _sum([r.deepSleepTime for r in records]),
        "lowSleepTime": _sum([r.lowSleepTime for r in records]),
        "allSleepTime": _sum([r.allSleepTime for r in records]),
        "segmentCount": len(records),
        "sleepDown": _earliest([r.startDateTime for r in records]),
        "sleepUp": _latest([r.endDateTime for r in records]),
        "sleepLine": _merge_sleep_line(records),
    }


def upload_sleep(db: Session, body: SleepUploadRequest) -> DeviceRecord | None:
    device = db.query(DeviceRecord).filter(DeviceRecord.mac_address == body.macAddress).first()
    if device is None:
        return None

    sorted_records = sorted(body.sleepRecords, key=_sort_key)
    sleep_records = [r.model_dump() for r in sorted_records]
    sleep_summary = _compute_summary(sorted_records)

    existing = db.query(SleepRecord).filter(
        SleepRecord.device_id == device.id,
        SleepRecord.date == body.date,
    ).first()

    if existing is None:
        db.add(SleepRecord(
            device_id=device.id,
            date=body.date,
            sleep_records=sleep_records,
            sleep_summary=sleep_summary,
        ))
    else:
        existing.sleep_records = sleep_records
        existing.sleep_summary = sleep_summary
    db.commit()
    return device


def get_sleep(db: Session, mac_address: str, date: str) -> SleepDataResponse | None:
    device = db.query(DeviceRecord).filter(DeviceRecord.mac_address == mac_address).first()
    if device is None:
        return None

    record = db.query(SleepRecord).filter(
        SleepRecord.device_id == device.id,
        SleepRecord.date == date,
    ).first()
    if record is None:
        return None

    return SleepDataResponse(
        id=record.id,
        macAddress=mac_address,
        date=record.date,
        sleepRecords=record.sleep_records or [],
        sleepSummary=record.sleep_summary,
    )
