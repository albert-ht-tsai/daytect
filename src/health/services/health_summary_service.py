import json
from datetime import datetime, time as time_cls, timezone

from fastapi import BackgroundTasks, HTTPException, status
from sqlalchemy.orm import Session

from src.core import ai_client
from src.core.database import engine
from src.core.logging import logger
from src.device.models.device_model import Device
from src.health.models.ai_health_summary_model import AiHealthSummaryChunk, AiHealthSummaryJob
from src.health.models.health_record_model import HealthRecord
from src.health.services.health_service import (
    _windowed_activity,
    _windowed_avg,
    _windowed_avg_min_max,
    _windowed_blood_pressure,
)

_TIME_WINDOWS: list[tuple[str, str]] = [
    ("00:00:00", "03:59:59"),
    ("04:00:00", "07:59:59"),
    ("08:00:00", "11:59:59"),
    ("12:00:00", "15:59:59"),
    ("16:00:00", "19:59:59"),
    ("20:00:00", "23:59:59"),
]

_BATCH_SYSTEM_PROMPT = """You are a health data analysis assistant.

Analyze the following time-window wearable health data batch.

Return a structured JSON object with these exact fields:
{
  "batch_index": <number>,
  "time_range": {"start_time": "<HH:MM:SS>", "end_time": "<HH:MM:SS>"},
  "key_findings": ["<string>"],
  "attention_metrics": ["<metric_key>"],
  "normal_metrics": ["<metric_key>"],
  "suggestions": ["<string>"],
  "data_quality_note": "<string>"
}

Rules:
- Do not diagnose disease or recommend medication or medical treatment.
- Do not overstate risks.
- Analyze only the provided batch data and time window.
- If data is insufficient, state it clearly in data_quality_note.
- Return JSON only."""

_FINAL_SYSTEM_PROMPT = """You are a health data analysis assistant.

You will receive a full day's health data from multiple time-window batch analyses.

Return a structured JSON object with these exact fields:
{
  "title": "<string>",
  "subtitle": "<string>",
  "metrics": [
    {
      "key": "<metric_key>",
      "title": "<display_title>",
      "value": <number|string|null>,
      "unit": "<unit|null>",
      "status": "Normal|Attention|Warning"
    }
  ],
  "suggestions": ["<string>"],
  "note": "<string>"
}

Rules:
- Do not diagnose disease or recommend medication or medical treatment.
- Do not overstate risks.
- Base the summary only on the provided data.
- If data is insufficient, mention it clearly in the note.
- Use clear and simple language.
- Return JSON only."""


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _fmt_ts_ms(dt: datetime | None) -> int | None:
    return int(dt.timestamp() * 1000) if dt else None


def _build_batch_metrics(record: HealthRecord, start_t: time_cls, end_t: time_cls) -> dict:
    metrics: dict = {}

    if record.heart_rate:
        wm = _windowed_avg_min_max(record.heart_rate, start_t, end_t)
        if any(v is not None for v in wm.values()):
            metrics["heart_rate"] = {**wm, "unit": "bpm"}

    if record.blood_pressure:
        wm = _windowed_blood_pressure(record.blood_pressure, start_t, end_t)
        if any(v is not None for v in wm.values()):
            metrics["blood_pressure"] = {**wm, "unit": "mmHg"}

    if record.blood_oxygen:
        wm = _windowed_avg_min_max(record.blood_oxygen, start_t, end_t)
        if any(v is not None for v in wm.values()):
            metrics["blood_oxygen"] = {**wm, "unit": "%"}

    if record.body_temperature:
        avg = _windowed_avg(record.body_temperature, start_t, end_t)
        if avg is not None:
            metrics["body_temperature"] = {"avg": avg, "unit": "°C"}

    if record.skin_temperature:
        avg = _windowed_avg(record.skin_temperature, start_t, end_t)
        if avg is not None:
            metrics["skin_temperature"] = {"avg": avg, "unit": "°C"}

    if record.respiratory_rate:
        avg = _windowed_avg(record.respiratory_rate, start_t, end_t)
        if avg is not None:
            metrics["respiratory_rate"] = {"avg": avg, "unit": "times/min"}

    if record.cardiac_load:
        avg = _windowed_avg(record.cardiac_load, start_t, end_t)
        if avg is not None:
            metrics["cardiac_load"] = {"avg": avg}

    if record.activity:
        wa = _windowed_activity(record.activity, start_t, end_t)
        if any(v is not None for v in wa.values()):
            metrics["activity"] = wa

    return metrics


def _build_daily_metrics(record: HealthRecord) -> dict:
    full_start = time_cls(0, 0, 0)
    full_end = time_cls(23, 59, 59)
    metrics = _build_batch_metrics(record, full_start, full_end)

    if record.sleep:
        s = record.sleep
        metrics["sleep"] = {
            "sleepQuality": s.get("sleepQuality"),
            "allSleepTime": s.get("allSleepTime"),
            "deepSleepTime": s.get("deepSleepTime"),
            "wakeCount": s.get("wakeCount"),
            "sleepDown": s.get("sleepDown"),
            "sleepUp": s.get("sleepUp"),
        }

    return metrics


# ── POST /health/{device_id}/summary/request ────────────────────────────────


def request_summary(db: Session, device: Device, date_str: str, background_tasks: BackgroundTasks) -> dict:
    from datetime import date as date_cls

    try:
        date_cls.fromisoformat(date_str)
    except ValueError:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, detail={"code": 400, "message": "Invalid date format"})

    job = AiHealthSummaryJob(
        device_id=device.id,
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

    background_tasks.add_task(_run_summary_pipeline, device.id, job.id)

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


# ── GET /health/{device_id}/summary/progress ────────────────────────────────


def _get_owned_job(db: Session, device: Device, job_id: str) -> AiHealthSummaryJob:
    job = (
        db.query(AiHealthSummaryJob)
        .filter(AiHealthSummaryJob.job_id == job_id, AiHealthSummaryJob.device_id == device.id)
        .first()
    )
    if job is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail={"code": 404, "message": "Summary job not found."})
    return job


def get_progress(db: Session, device: Device, job_id: str) -> dict:
    job = _get_owned_job(db, device, job_id)
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


# ── GET /health/{device_id}/summary/result ──────────────────────────────────


def get_result(db: Session, device: Device, job_id: str) -> dict:
    job = _get_owned_job(db, device, job_id)
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


# ── Pipeline (runs in BackgroundTasks threadpool) ────────────────────────────


def _mark_failed(db: Session, job: AiHealthSummaryJob, message: str) -> None:
    job.status = "failed"
    job.progress_state = "Failed"
    job.progress_message = message
    job.error_message = message
    db.add(job)
    db.commit()


def _run_summary_pipeline(device_id: int, job_pk: int) -> None:
    with Session(engine) as db:
        job = db.get(AiHealthSummaryJob, job_pk)
        if job is None:
            return
        try:
            _execute_pipeline(db, job, device_id)
        except Exception as e:  # noqa: BLE001
            logger.exception("Summary pipeline crashed for job %s", job.job_id)
            db.rollback()
            job = db.get(AiHealthSummaryJob, job_pk)
            if job is not None and job.status not in ("done", "failed"):
                _mark_failed(db, job, str(e))


def _execute_pipeline(db: Session, job: AiHealthSummaryJob, device_id: int) -> None:
    from datetime import date as date_cls

    job.status = "processing"
    job.progress_state = "Reading"
    job.progress_message = "Reading health data..."
    db.commit()

    record_date = date_cls.fromisoformat(job.date.isoformat())
    record = (
        db.query(HealthRecord)
        .filter(HealthRecord.device_id == device_id, HealthRecord.date == record_date)
        .first()
    )

    if record is None:
        _mark_failed(db, job, "No health data found for the specified date.")
        return

    job.progress_state = "Analyzing"
    job.progress_message = "Analyzing health data..."
    job.batch_count = len(_TIME_WINDOWS)
    db.commit()

    chunks: list[AiHealthSummaryChunk] = []
    for idx, (start_str, end_str) in enumerate(_TIME_WINDOWS, start=1):
        chunk = AiHealthSummaryChunk(
            job_id=job.id,
            batch_index=idx,
            start_time=start_str,
            end_time=end_str,
            status="pending",
        )
        db.add(chunk)
        chunks.append(chunk)
    db.commit()
    for c in chunks:
        db.refresh(c)

    job.progress_state = "Summarizing"
    job.progress_message = "Generating health summary..."
    db.commit()

    partial_summaries: list[dict] = []
    for chunk in chunks:
        start_t = time_cls.fromisoformat(chunk.start_time)
        end_t = time_cls.fromisoformat(chunk.end_time)

        metrics = _build_batch_metrics(record, start_t, end_t)
        key_metric_keys = ["heart_rate", "blood_pressure", "blood_oxygen", "activity"]
        missing_fields = [k for k in key_metric_keys if k not in metrics]
        has_enough_data = len(missing_fields) < len(key_metric_keys)

        batch_input = {
            "job_id": job.job_id,
            "device_id": device_id,
            "date": job.date.isoformat(),
            "batch_index": chunk.batch_index,
            "batch_count": job.batch_count,
            "time_range": {"start_time": chunk.start_time, "end_time": chunk.end_time},
            "metrics": metrics,
            "data_quality": {"missing_fields": missing_fields, "has_enough_data": has_enough_data},
        }

        chunk.status = "processing"
        chunk.input_json = batch_input
        db.commit()

        try:
            partial_result, _ = ai_client.generate_json(
                _BATCH_SYSTEM_PROMPT,
                f"Input:\n{json.dumps(batch_input, default=str)}",
            )
        except Exception as e:  # noqa: BLE001
            chunk.status = "failed"
            chunk.error_message = str(e)
            db.commit()
            _mark_failed(db, job, f"Batch {chunk.batch_index} failed: {e}")
            return

        chunk.status = "completed"
        chunk.partial_summary_json = partial_result
        db.commit()

        partial_summaries.append(partial_result)
        job.completed_batch_count += 1
        job.progress_message = f"Generating health summary... ({job.completed_batch_count}/{job.batch_count})"
        db.commit()

    daily_metrics = _build_daily_metrics(record)

    final_input = {
        "device_id": device_id,
        "date": job.date.isoformat(),
        "period": {"start_time": "00:00:00", "end_time": "23:59:59"},
        "daily_metrics": daily_metrics,
        "partial_summaries": partial_summaries,
    }

    try:
        final_result, _ = ai_client.generate_json(
            _FINAL_SYSTEM_PROMPT,
            f"Input:\n{json.dumps(final_input, default=str)}",
        )
    except Exception as e:  # noqa: BLE001
        _mark_failed(db, job, f"Final summary generation failed: {e}")
        return

    now = _now()
    job.status = "done"
    job.progress_state = "Done"
    job.progress_message = "Health summary generated."
    job.final_summary_json = final_result
    job.completed_at = now
    db.add(job)
    db.commit()
