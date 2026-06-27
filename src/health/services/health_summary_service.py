from datetime import datetime, timezone

from fastapi import HTTPException, status
from sqlalchemy.orm import Session

from src.health.models.ai_health_summary_model import AiHealthSummaryJob


def _fmt_ts_ms(dt: datetime | None) -> int | None:
    return int(dt.timestamp() * 1000) if dt else None


# ── POST /health/summary/request ────────────────────────────────────────────


def request_summary(db: Session, user_id: int, date_str: str) -> dict:
    from datetime import date as date_cls

    try:
        date_cls.fromisoformat(date_str)
    except ValueError:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, detail={"code": 400, "message": "Invalid date format"})

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


# ── GET /health/summary/progress ────────────────────────────────────────────


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


# ── GET /health/summary/result ───────────────────────────────────────────────


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
