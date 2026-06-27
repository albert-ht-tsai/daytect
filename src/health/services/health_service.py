from datetime import date as date_cls
from datetime import datetime, timezone

from sqlalchemy.orm import Session

from src.health.models.activity_record_model import ActivityRecord
from src.health.models.health_record_model import HealthRecord
from src.health.models.sleep_record_model import SleepRecord
from src.health.schemas.health_schema import UploadHealthRequest


def _parse_datetime(dt_str: str) -> datetime | None:
    try:
        return datetime.strptime(dt_str, "%Y-%m-%d %H:%M:%S")
    except (ValueError, TypeError):
        return None


def upload_health(db: Session, user_id: int, body: UploadHealthRequest) -> None:
    # ── 1. sleep_records ──────────────────────────────────────────────────
    for s in body.sleep_records:
        if not s.date:
            continue
        try:
            sleep_date = date_cls.fromisoformat(s.date)
        except (ValueError, TypeError):
            continue
        existing = (
            db.query(SleepRecord)
            .filter(SleepRecord.user_id == user_id, SleepRecord.date == sleep_date)
            .first()
        )
        if existing is None:
            db.add(SleepRecord(
                user_id=user_id,
                date=sleep_date,
                sleep_quality=s.sleepQuality,
                wake_count=s.wakeCount,
                deep_sleep_time=s.deepSleepTime,
                low_sleep_time=s.lowSleepTime,
                all_sleep_time=s.allSleepTime,
                sleep_down=s.sleepDown,
                sleep_up=s.sleepUp,
                sleep_line=s.sleepLine,
            ))
        else:
            for attr, val in (
                ("sleep_quality", s.sleepQuality),
                ("wake_count", s.wakeCount),
                ("deep_sleep_time", s.deepSleepTime),
                ("low_sleep_time", s.lowSleepTime),
                ("all_sleep_time", s.allSleepTime),
                ("sleep_down", s.sleepDown),
                ("sleep_up", s.sleepUp),
                ("sleep_line", s.sleepLine),
            ):
                if val is not None:
                    setattr(existing, attr, val)
            existing.updated_at = datetime.now(timezone.utc)

    # ── 2. health_records ──────────────────────────────────────────────────
    for r in body.health_records:
        dt = _parse_datetime(r.datetime)
        if dt is None:
            continue
        try:
            record_date = date_cls.fromisoformat(r.date)
        except (ValueError, TypeError):
            continue
        d = r.data
        bc = d.bloodComponent.model_dump(exclude_none=True) if d.bloodComponent else None
        existing = (
            db.query(HealthRecord)
            .filter(HealthRecord.user_id == user_id, HealthRecord.datetime == dt)
            .first()
        )
        if existing is None:
            db.add(HealthRecord(
                user_id=user_id,
                date=record_date,
                datetime=dt,
                heart_rate=d.heartRate,
                blood_oxygen=d.bloodOxygen,
                respiratory_rate=d.respiratoryRate,
                sleep_state=d.sleepState,
                apnea_result=d.apneaResult,
                hypoxia_time=d.hypoxiaTime,
                cardiac_load=d.cardiacLoad,
                is_hypoxia=d.isHypoxia,
                correct=d.correct,
                blood_glucose=d.bloodGlucose,
                sport_status=d.sportStatus,
                blood_component=bc,
            ))
        else:
            for attr, val in (
                ("heart_rate", d.heartRate),
                ("blood_oxygen", d.bloodOxygen),
                ("respiratory_rate", d.respiratoryRate),
                ("sleep_state", d.sleepState),
                ("apnea_result", d.apneaResult),
                ("hypoxia_time", d.hypoxiaTime),
                ("cardiac_load", d.cardiacLoad),
                ("is_hypoxia", d.isHypoxia),
                ("correct", d.correct),
                ("blood_glucose", d.bloodGlucose),
                ("sport_status", d.sportStatus),
            ):
                if val is not None:
                    setattr(existing, attr, val)
            if bc is not None:
                existing.blood_component = bc
            existing.updated_at = datetime.now(timezone.utc)

    # ── 3. activity_records ────────────────────────────────────────────────
    for a in body.activity_records:
        dt = _parse_datetime(a.datetime)
        if dt is None:
            continue
        try:
            record_date = date_cls.fromisoformat(a.date)
        except (ValueError, TypeError):
            continue
        d = a.data
        existing = (
            db.query(ActivityRecord)
            .filter(ActivityRecord.user_id == user_id, ActivityRecord.datetime == dt)
            .first()
        )
        if existing is None:
            db.add(ActivityRecord(
                user_id=user_id,
                date=record_date,
                datetime=dt,
                sport_value=d.sportValue,
                step_value=d.stepValue,
                wear=d.wear,
                cal_value=d.calValue,
                dis_value=d.disValue,
            ))
        else:
            for attr, val in (
                ("sport_value", d.sportValue),
                ("step_value", d.stepValue),
                ("wear", d.wear),
                ("cal_value", d.calValue),
                ("dis_value", d.disValue),
            ):
                if val is not None:
                    setattr(existing, attr, val)
            existing.updated_at = datetime.now(timezone.utc)

    db.commit()
