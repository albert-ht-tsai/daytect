import json
from datetime import date as date_cls
from datetime import datetime, timedelta, timezone

from fastapi import HTTPException, status
from sqlalchemy.orm import Session

from src.core.ai_client import AIResponseFormatError, generate_json
from src.core.database import SessionLocal
from src.core.logging import logger
from src.health.models.activity_record_model import ActivityRecord
from src.health.models.ai_health_summary_model import AiHealthSummaryChunk, AiHealthSummaryJob
from src.health.models.health_record_model import HealthRecord
from src.health.models.sleep_record_model import SleepRecord
from src.health.services import health_rules

# ── Time windows ─────────────────────────────────────────────────────────────

_WINDOWS = [
    ("Night",     "00:00", "05:59"),
    ("Morning",   "06:00", "11:59"),
    ("Afternoon", "12:00", "17:59"),
    ("Evening",   "18:00", "23:59"),
]

# ── OpenAI prompts ────────────────────────────────────────────────────────────

_CHUNK_SYSTEM = (
    "You are a professional health data analyst. "
    "Analyze the health and activity sensor data for the given time window and return a concise JSON partial summary. "
    "Null values mean the sensor had no reading — do not infer or fabricate data."
)

_MERGE_SYSTEM = (
    "You are a professional health data analyst. "
    "Synthesize the partial time-window health summaries below into a single comprehensive daily health report JSON. "
    "Be concise, factual, and medically responsible. Do not invent data that was not provided."
)

# ── Data helpers ──────────────────────────────────────────────────────────────


def _avg(values: list) -> float | None:
    clean = [v for v in values if v is not None]
    return round(sum(clean) / len(clean), 2) if clean else None


def _in_window(dt: datetime, start: str, end: str) -> bool:
    sh, sm = map(int, start.split(":"))
    eh, em = map(int, end.split(":"))
    t = dt.hour * 60 + dt.minute
    return sh * 60 + sm <= t <= eh * 60 + em


def _serialize_health(records: list) -> list[dict]:
    return [
        {
            "time": r.datetime.strftime("%H:%M"),
            "heartRate": r.heart_rate,
            "bloodOxygen": r.blood_oxygen,
            "respiratoryRate": r.respiratory_rate,
            "sleepState": r.sleep_state,
            "apneaResult": r.apnea_result,
            "hypoxiaTime": r.hypoxia_time,
            "cardiacLoad": r.cardiac_load,
            "isHypoxia": r.is_hypoxia,
            "bloodGlucose": r.blood_glucose,
            "sportStatus": r.sport_status,
        }
        for r in records
    ]


def _serialize_activity(records: list) -> list[dict]:
    return [
        {
            "time": r.datetime.strftime("%H:%M"),
            "stepValue": r.step_value,
            "calValue": r.cal_value,
            "disValue": r.dis_value,
            "sportValue": r.sport_value,
            "wear": r.wear,
        }
        for r in records
    ]


def _serialize_sleep(sleep) -> dict:
    if sleep is None:
        return {}
    return {
        "sleepQuality": sleep.sleep_quality,
        "wakeCount": sleep.wake_count,
        "deepSleepTime": sleep.deep_sleep_time,
        "lowSleepTime": sleep.low_sleep_time,
        "allSleepTime": sleep.all_sleep_time,
        "sleepDown": sleep.sleep_down,
        "sleepUp": sleep.sleep_up,
    }


def _compute_trends(
    today_health: list,
    prev_health: list,
    today_sleep,
    prev_sleep,
    today_activity: list,
    prev_activity: list,
) -> dict:
    def health_avgs(records):
        return {
            "heart_rate": _avg([r.heart_rate for r in records]),
            "blood_oxygen": _avg([r.blood_oxygen for r in records]),
            "respiratory_rate": _avg([r.respiratory_rate for r in records]),
            "cardiac_load": _avg([r.cardiac_load for r in records]),
        }

    def activity_totals(records):
        return {
            "steps": sum(r.step_value or 0 for r in records),
            "calories": round(sum(r.cal_value or 0.0 for r in records), 2),
            "disValue": round(sum(r.dis_value or 0.0 for r in records), 2),
            "sportValue": _avg([r.sport_value for r in records]),
        }

    def sleep_dict(s):
        if s is None:
            return {}
        return {
            "sleepQuality": s.sleep_quality,
            "allSleepTime": s.all_sleep_time,
            "deepSleepTime": s.deep_sleep_time,
            "wakeCount": s.wake_count,
        }

    cur_h = health_avgs(today_health)
    prev_h = health_avgs(prev_health)
    cur_a = activity_totals(today_activity)
    prev_a = activity_totals(prev_activity)

    return {
        "heartRate": health_rules.heart_rate_status(cur_h["heart_rate"], prev_h["heart_rate"]),
        "bloodOxygen": health_rules.blood_oxygen_status(cur_h["blood_oxygen"], prev_h["blood_oxygen"]),
        "respiratoryRate": health_rules.respiratory_rate_status(cur_h["respiratory_rate"], prev_h["respiratory_rate"]),
        "cardiacLoad": health_rules.cardiac_load_status(cur_h["cardiac_load"], prev_h["cardiac_load"]),
        "activity": health_rules.activity_status(cur_a, prev_a),
        "sleep": health_rules.sleep_status(sleep_dict(today_sleep), sleep_dict(prev_sleep)),
    }


# ── Prompt builders ───────────────────────────────────────────────────────────


def _chunk_user_prompt(
    label: str, start: str, end: str, date_str: str,
    health_rows: list[dict], activity_rows: list[dict],
) -> str:
    return (
        f"Date: {date_str}  |  Time window: {label} ({start}–{end})\n\n"
        f"Health records (30-min slots, null = no sensor reading):\n"
        f"{json.dumps(health_rows, ensure_ascii=False)}\n\n"
        f"Activity records (30-min slots):\n"
        f"{json.dumps(activity_rows, ensure_ascii=False)}\n\n"
        "Return JSON with exactly these keys:\n"
        '  "window": string,\n'
        '  "avg_heart_rate": float or null,\n'
        '  "avg_blood_oxygen": float or null,\n'
        '  "avg_respiratory_rate": float or null,\n'
        '  "total_steps": int,\n'
        '  "total_calories": float,\n'
        '  "notable_findings": list of strings (max 3),\n'
        '  "window_status": "normal" | "attention" | "alert"'
    )


def _merge_user_prompt(
    date_str: str,
    partials: list[dict],
    sleep: dict,
    trends: dict,
) -> str:
    return (
        f"Date: {date_str}\n\n"
        f"Time-window partial summaries:\n{json.dumps(partials, ensure_ascii=False)}\n\n"
        f"Sleep data for the day:\n{json.dumps(sleep, ensure_ascii=False)}\n\n"
        f"Metric trends vs previous day (improve / stable / decrease):\n{json.dumps(trends, ensure_ascii=False)}\n\n"
        "Return a comprehensive daily health summary JSON with exactly these keys:\n"
        '  "overall_status": "normal" | "attention" | "alert",\n'
        '  "sleep": {\n'
        '    "status": "improve" | "stable" | "decrease",\n'
        '    "summary": string,\n'
        '    "quality_score": int or null,\n'
        '    "duration_minutes": int or null\n'
        '  },\n'
        '  "vitals": {\n'
        '    "status": "improve" | "stable" | "decrease",\n'
        '    "summary": string,\n'
        '    "avg_heart_rate": float or null,\n'
        '    "avg_blood_oxygen": float or null\n'
        '  },\n'
        '  "activity": {\n'
        '    "status": "improve" | "stable" | "decrease",\n'
        '    "summary": string,\n'
        '    "total_steps": int,\n'
        '    "total_calories": float\n'
        '  },\n'
        '  "highlights": list of strings (max 5),\n'
        '  "recommendations": list of strings (max 3)'
    )


# ── Background pipeline ───────────────────────────────────────────────────────


def run_summary_pipeline(job_pk: int) -> None:
    """Background task: read DB data → chunk → OpenAI per chunk → merge → write result."""
    db: Session = SessionLocal()
    try:
        job = db.query(AiHealthSummaryJob).filter(AiHealthSummaryJob.id == job_pk).first()
        if job is None:
            logger.error("run_summary_pipeline: job pk=%d not found", job_pk)
            return

        target_date = job.date
        user_id = job.user_id
        prev_date = target_date - timedelta(days=1)
        date_str = target_date.isoformat()

        # ── Step 1: Fetch data ────────────────────────────────────────────
        today_health = (
            db.query(HealthRecord)
            .filter(HealthRecord.user_id == user_id, HealthRecord.date == target_date)
            .order_by(HealthRecord.datetime)
            .all()
        )
        today_activity = (
            db.query(ActivityRecord)
            .filter(ActivityRecord.user_id == user_id, ActivityRecord.date == target_date)
            .order_by(ActivityRecord.datetime)
            .all()
        )
        today_sleep = (
            db.query(SleepRecord)
            .filter(SleepRecord.user_id == user_id, SleepRecord.date == target_date)
            .first()
        )
        prev_health = (
            db.query(HealthRecord)
            .filter(HealthRecord.user_id == user_id, HealthRecord.date == prev_date)
            .all()
        )
        prev_activity = (
            db.query(ActivityRecord)
            .filter(ActivityRecord.user_id == user_id, ActivityRecord.date == prev_date)
            .all()
        )
        prev_sleep = (
            db.query(SleepRecord)
            .filter(SleepRecord.user_id == user_id, SleepRecord.date == prev_date)
            .first()
        )

        # ── Step 2: Pre-compute trends vs previous day ────────────────────
        trends = _compute_trends(
            today_health, prev_health,
            today_sleep, prev_sleep,
            today_activity, prev_activity,
        )

        # ── Step 3: Assign records to time windows ────────────────────────
        non_empty_windows = []
        for label, start, end in _WINDOWS:
            h = [r for r in today_health if _in_window(r.datetime, start, end)]
            a = [r for r in today_activity if _in_window(r.datetime, start, end)]
            if h or a:
                non_empty_windows.append((label, start, end, h, a))

        if not non_empty_windows:
            _mark_failed(db, job, "No health or activity data found for this date.")
            return

        job.status = "processing"
        job.progress_state = "Processing"
        job.progress_message = "Analyzing time windows..."
        job.batch_count = len(non_empty_windows)
        job.completed_batch_count = 0
        db.commit()

        # ── Step 4: Call OpenAI for each time-window chunk ────────────────
        partial_summaries: list[dict] = []
        for batch_index, (label, start, end, h_recs, a_recs) in enumerate(non_empty_windows):
            h_rows = _serialize_health(h_recs)
            a_rows = _serialize_activity(a_recs)

            chunk = AiHealthSummaryChunk(
                job_id=job.id,
                batch_index=batch_index,
                start_time=start,
                end_time=end,
                status="processing",
                input_json={"health": h_rows, "activity": a_rows},
            )
            db.add(chunk)
            db.commit()
            db.refresh(chunk)

            try:
                partial_json, _ = generate_json(
                    _CHUNK_SYSTEM,
                    _chunk_user_prompt(label, start, end, date_str, h_rows, a_rows),
                )
                chunk.partial_summary_json = partial_json
                chunk.status = "done"
                partial_summaries.append(partial_json)
            except (AIResponseFormatError, Exception) as exc:
                chunk.status = "failed"
                chunk.error_message = str(exc)
                logger.warning("Summary chunk %d failed for job %s: %s", batch_index, job.job_id, exc)
                # Include error placeholder so merge still runs with remaining windows
                partial_summaries.append({"window": label, "note": "data unavailable for this window"})

            job.completed_batch_count = batch_index + 1
            job.progress_message = f"Analyzed {batch_index + 1} of {len(non_empty_windows)} time windows"
            db.commit()

        # ── Step 5: Merge all partials into final summary ─────────────────
        job.progress_state = "Finalizing"
        job.progress_message = "Generating final daily health report..."
        db.commit()

        sleep_data = _serialize_sleep(today_sleep)
        try:
            final_json, _ = generate_json(
                _MERGE_SYSTEM,
                _merge_user_prompt(date_str, partial_summaries, sleep_data, trends),
            )
        except (AIResponseFormatError, Exception) as exc:
            _mark_failed(db, job, f"Final merge failed: {exc}")
            return

        final_json["date"] = date_str
        job.final_summary_json = final_json
        job.status = "done"
        job.progress_state = "Done"
        job.progress_message = "Health summary ready."
        job.completed_at = datetime.now(timezone.utc)
        db.commit()
        logger.info("Summary job %s completed (user=%d, date=%s)", job.job_id, user_id, date_str)

    except Exception:
        logger.exception("Unhandled error in summary pipeline for job pk=%d", job_pk)
        try:
            job = db.query(AiHealthSummaryJob).filter(AiHealthSummaryJob.id == job_pk).first()
            if job:
                _mark_failed(db, job, "Internal pipeline error.")
        except Exception:
            pass
    finally:
        db.close()


def _mark_failed(db: Session, job: AiHealthSummaryJob, message: str) -> None:
    job.status = "failed"
    job.progress_state = "Failed"
    job.progress_message = message
    job.error_message = message
    job.completed_at = datetime.now(timezone.utc)
    db.commit()
    logger.error("Summary job %s failed: %s", job.job_id, message)


# ── CRUD endpoints ────────────────────────────────────────────────────────────


def _fmt_ts_ms(dt: datetime | None) -> int | None:
    return int(dt.timestamp() * 1000) if dt else None


def request_summary(db: Session, user_id: int, date_str: str) -> tuple[dict, int]:
    """Create a summary job. Returns (response_payload, job_pk) for the caller to schedule the pipeline."""
    try:
        date_cls.fromisoformat(date_str)
    except ValueError:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, detail={"code": 400, "message": "Invalid date format. Use YYYY-MM-DD."})

    job = AiHealthSummaryJob(
        user_id=user_id,
        date=date_str,
        status="queued",
        progress_state="Queued",
        progress_message="Waiting to start...",
        batch_count=0,
        completed_batch_count=0,
    )
    db.add(job)
    db.commit()
    db.refresh(job)

    payload = {
        "job_id": job.job_id,
        "status": job.status,
        "progress": {
            "state": job.progress_state,
            "message": job.progress_message,
            "completed_batch_count": job.completed_batch_count,
            "batch_count": job.batch_count,
        },
    }
    return payload, job.id


def _get_owned_job(db: Session, user_id: int, job_id: str) -> AiHealthSummaryJob:
    job = (
        db.query(AiHealthSummaryJob)
        .filter(AiHealthSummaryJob.job_id == job_id, AiHealthSummaryJob.user_id == user_id)
        .first()
    )
    if job is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail={"code": 404, "message": "Summary job not found."})
    return job


def get_progress(db: Session, user_id: int, job_id: str) -> dict:
    job = _get_owned_job(db, user_id, job_id)
    return {
        "job_id": job.job_id,
        "status": job.status,
        "progress": {
            "state": job.progress_state,
            "message": job.progress_message,
            "completed_batch_count": job.completed_batch_count,
            "batch_count": job.batch_count,
        },
    }


def get_result(db: Session, user_id: int, job_id: str) -> dict:
    job = _get_owned_job(db, user_id, job_id)
    if job.status != "done":
        raise HTTPException(
            status.HTTP_400_BAD_REQUEST,
            detail={"code": 400, "message": "Summary not ready yet.", "status": job.status},
        )

    summary = dict(job.final_summary_json or {})
    summary["created_at"] = _fmt_ts_ms(job.completed_at or job.created_at)

    return {
        "job_id": job.job_id,
        "status": "done",
        "date": job.date.isoformat(),
        "summary": summary,
    }
