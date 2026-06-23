import json
from datetime import datetime, timezone

from fastapi import BackgroundTasks, HTTPException, status
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from src.core import ai_client
from src.core.database import engine
from src.core.logging import logger
from src.device.models.device_model import Device
from src.health.services import health_service
from src.report.models import ReportBatch, ReportResult, ReportTask
from src.report.schemas.report_schema import CreateReportTaskRequest
from src.report.services import token_utils

_FULL_DAY_START = "00:00:00"
_FULL_DAY_END = "23:59:59"

_STEP_KEYS = ["prepare_data", "split_batches", "analyze_batches", "generate_final_report"]

_STEP_MESSAGES = {
    "prepare_data": {
        "pending": "Waiting to prepare health data.",
        "processing": "Preparing health data.",
        "completed": "Health data prepared successfully.",
        "failed": "Failed to prepare health data.",
    },
    "split_batches": {
        "pending": "Waiting to split health data.",
        "processing": "Splitting health data by token limit.",
        "completed": "Health data split by token limit.",
        "failed": "Failed to split health data.",
    },
    "analyze_batches": {
        "pending": "Waiting for batch analysis.",
        "processing": "Batch analysis is in progress.",
        "completed": "Batch analysis completed.",
        "failed": "Batch analysis failed.",
    },
    "generate_final_report": {
        "pending": "Waiting for all batch analysis results.",
        "processing": "Generating final report.",
        "completed": "Final report generated.",
        "failed": "Failed to generate final report.",
    },
}

_STATUS_STAGE_INDEX = {
    "queued": -1,
    "preparing": 0,
    "splitting": 1,
    "processing": 2,
    "finalizing": 3,
    "completed": 4,
}

_BATCH_SYSTEM_PROMPT = """You are a health data analysis assistant.

Analyze the following wearable health data batch.

Return a structured JSON result.

The result must include:
1. summary
2. abnormal_points
3. risk_signals
4. suggestions
5. data_quality

Rules:
- Do not diagnose disease.
- Do not overstate risks.
- Analyze only the provided batch data.
- Focus on trends, abnormal changes and possible lifestyle signals.
- If data is insufficient, mention it clearly.
- Return JSON only.
- Write all text fields in the following language: {language}."""

_FINAL_SYSTEM_PROMPT = """You are a health data analysis assistant.

You will receive:
1. overall health statistics
2. multiple batch analysis results
3. abnormal points
4. risk signals
5. missing data information
6. token usage summary

Generate the final health report.

Return a structured JSON result.

The result must include:
1. health_summary
2. possible_risks
3. improvement_suggestions
4. attention_level
5. data_quality
6. disclaimer

Rules:
- Do not diagnose disease.
- Do not claim severe risk unless the data clearly supports it.
- Base the final report only on the provided statistics and batch results.
- Mention missing or insufficient data if applicable.
- Use clear and simple language.
- Return JSON only.
- Write all text fields in the following language: {language}."""


def _fmt(dt: datetime | None) -> str | None:
    return dt.strftime("%Y-%m-%d %H:%M:%S") if dt else None


def _now() -> datetime:
    return datetime.now(timezone.utc)


# ── POST /reports/{device_id}/tasks ─────────────────────────────────────────


def create_task(
    db: Session, device: Device, body: CreateReportTaskRequest, background_tasks: BackgroundTasks
) -> dict:
    task = ReportTask(
        device_id=device.id,
        report_type=body.report_type,
        date=body.date,
        language=body.language,
        status="queued",
        current_step="Task created",
        progress_message="AI health report task has been created.",
    )
    db.add(task)
    try:
        db.commit()
    except IntegrityError:
        db.rollback()
        task = (
            db.query(ReportTask)
            .filter(
                ReportTask.device_id == device.id,
                ReportTask.report_type == body.report_type,
                ReportTask.date == body.date,
            )
            .first()
        )
    else:
        db.refresh(task)
        background_tasks.add_task(_run_report_pipeline, device.id, task.id)

    return {
        "report_task_id": task.report_task_id,
        "device_id": task.device_id,
        "report_type": task.report_type,
        "date": task.date.isoformat(),
        "status": task.status,
        "progress": {
            "percentage": task.progress_percentage,
            "current_step": task.current_step,
            "message": task.progress_message,
        },
        "polling": {"recommended_interval_seconds": 10},
        "created_at": _fmt(task.created_at),
    }


# ── GET /reports/{device_id}/tasks/{report_task_id}/progress ───────────────


def _get_owned_task(db: Session, device: Device, report_task_id: str) -> ReportTask:
    task = (
        db.query(ReportTask)
        .filter(ReportTask.report_task_id == report_task_id, ReportTask.device_id == device.id)
        .first()
    )
    if task is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail={"code": 404, "message": "Report task not found."})
    return task


def _build_steps(task_status: str, failed_step: str | None) -> list[dict]:
    if task_status == "failed":
        fail_index = _STEP_KEYS.index(failed_step) if failed_step in _STEP_KEYS else 0
        steps = []
        for i, key in enumerate(_STEP_KEYS):
            step_status = "completed" if i < fail_index else "failed" if i == fail_index else "pending"
            steps.append({"step": key, "status": step_status, "message": _STEP_MESSAGES[key][step_status]})
        return steps

    stage_index = _STATUS_STAGE_INDEX.get(task_status, -1)
    steps = []
    for i, key in enumerate(_STEP_KEYS):
        if task_status == "completed" or i < stage_index:
            step_status = "completed"
        elif i == stage_index:
            step_status = "processing"
        else:
            step_status = "pending"
        steps.append({"step": key, "status": step_status, "message": _STEP_MESSAGES[key][step_status]})
    return steps


def get_progress(db: Session, device: Device, report_task_id: str) -> dict:
    task = _get_owned_task(db, device, report_task_id)

    base = {
        "report_task_id": task.report_task_id,
        "device_id": task.device_id,
        "report_type": task.report_type,
        "status": task.status,
        "progress": {
            "percentage": task.progress_percentage,
            "current_step": task.current_step,
            "message": task.progress_message,
            "total_batches": task.total_batches,
            "completed_batches": task.completed_batches,
            "processing_batches": task.processing_batches,
            "pending_batches": task.pending_batches,
            "failed_batches": task.failed_batches,
        },
    }

    if task.status == "completed":
        base["result_ready"] = True
        base["result_endpoint"] = f"/reports/{task.device_id}/tasks/{task.report_task_id}/result"
        base["completed_at"] = _fmt(task.completed_at)
        return base

    if task.status == "failed":
        base["failed_step"] = task.failed_step
        base["error_code"] = task.error_code
        base["error_message"] = task.error_message
        base["updated_at"] = _fmt(task.updated_at)
        return base

    base["steps"] = _build_steps(task.status, task.failed_step)
    base["token_usage"] = {
        "estimated_total_input_tokens": task.estimated_total_input_tokens,
        "actual_input_tokens": task.actual_total_input_tokens,
        "actual_output_tokens": task.actual_total_output_tokens,
        "total_tokens_used": task.actual_total_input_tokens + task.actual_total_output_tokens,
    }
    base["polling"] = {"recommended_interval_seconds": 10}
    base["updated_at"] = _fmt(task.updated_at)
    return base


# ── GET /reports/{device_id}/tasks/{report_task_id}/result ─────────────────


def get_task_for_result(db: Session, device: Device, report_task_id: str) -> ReportTask:
    return _get_owned_task(db, device, report_task_id)


def build_result_body(task: ReportTask) -> dict:
    result = task.result
    body = {
        "report_id": result.id,
        "report_task_id": task.report_task_id,
        "device_id": task.device_id,
        "report_type": task.report_type,
        "status": "completed",
        "overall_status": result.overall_status,
        "summary": result.summary,
        "ai_report": result.ai_report,
        "token_usage": result.token_usage,
        "created_at": _fmt(result.created_at),
        "completed_at": _fmt(result.completed_at),
    }
    if task.report_type == "weekly":
        body["week"] = result.date_range["current"]
        body["compare_week"] = result.date_range["previous"]
    else:
        body["date"] = result.date_range["current"]["start_date"]
        body["compare_date"] = result.date_range["previous"]["start_date"]
    return body


# ── POST /reports/{device_id}/tasks/{report_task_id}/retry ─────────────────


def retry_task(db: Session, device: Device, report_task_id: str, background_tasks: BackgroundTasks) -> dict:
    task = _get_owned_task(db, device, report_task_id)
    if task.status != "failed":
        raise HTTPException(
            status.HTTP_400_BAD_REQUEST, detail={"code": 400, "message": "Only failed tasks can be retried."}
        )

    db.query(ReportBatch).filter(ReportBatch.task_id == task.id).delete()
    task.status = "queued"
    task.progress_percentage = 0
    task.current_step = "Retry started"
    task.progress_message = "Report task has been restarted."
    task.failed_step = None
    task.error_code = None
    task.error_message = None
    task.total_batches = 0
    task.completed_batches = 0
    task.processing_batches = 0
    task.pending_batches = 0
    task.failed_batches = 0
    db.commit()
    db.refresh(task)

    background_tasks.add_task(_run_report_pipeline, device.id, task.id)

    return {
        "report_task_id": task.report_task_id,
        "status": task.status,
        "progress": {
            "percentage": task.progress_percentage,
            "current_step": task.current_step,
            "message": task.progress_message,
        },
    }


# ── Internal pipeline (runs in BackgroundTasks threadpool) ─────────────────


def _date_range(report_type: str, health_data: dict) -> dict:
    if report_type == "weekly":
        return {"current": health_data["week"], "previous": health_data["compare_week"]}
    return {
        "current": {"start_date": health_data["date"], "end_date": health_data["date"]},
        "previous": {"start_date": health_data["compare_date"], "end_date": health_data["compare_date"]},
    }


def _mark_failed(db: Session, task: ReportTask, error_code: str, error_message: str, failed_step: str | None) -> None:
    task.status = "failed"
    task.failed_step = failed_step
    task.error_code = error_code
    task.error_message = error_message
    task.current_step = "Failed"
    task.progress_message = error_message
    task.processing_batches = 0
    db.add(task)
    db.commit()


def _run_report_pipeline(device_id: int, task_pk: int) -> None:
    with Session(engine) as db:
        task = db.get(ReportTask, task_pk)
        if task is None:
            return
        try:
            _execute_pipeline(db, task, device_id)
        except Exception as e:  # noqa: BLE001 - last-resort guard for an unattended background task
            logger.exception("Report pipeline crashed for task %s", task.report_task_id)
            db.rollback()
            task = db.get(ReportTask, task_pk)
            if task is not None and task.status not in ("completed", "failed"):
                _mark_failed(db, task, "INTERNAL_ERROR", str(e), failed_step=None)


def _execute_pipeline(db: Session, task: ReportTask, device_id: int) -> None:
    device = db.get(Device, device_id)

    task.status = "preparing"
    task.current_step = "Preparing health data"
    task.progress_message = "Loading and preparing health data."
    task.progress_percentage = 5
    db.commit()

    date_str = task.date.isoformat()
    if task.report_type == "weekly":
        health_data = health_service.get_weekly_status(db, device, date_str, _FULL_DAY_START, _FULL_DAY_END)
    else:
        health_data = health_service.get_daily_status(db, device, date_str, _FULL_DAY_START, _FULL_DAY_END)

    if health_data is None:
        _mark_failed(db, task, "HEALTH_DATA_NOT_FOUND", "Health data not found.", failed_step="prepare_data")
        return

    task.status = "splitting"
    task.current_step = "Splitting health data by token limit"
    task.progress_message = "Organizing health data into batches."
    task.progress_percentage = 15
    db.commit()

    metrics = health_data["metrics"]
    batches = token_utils.split_into_batches(metrics)

    batch_rows: list[ReportBatch] = []
    estimated_total = 0
    for index, batch_metrics in enumerate(batches, start=1):
        estimated = token_utils.estimate_tokens(batch_metrics)
        estimated_total += estimated
        row = ReportBatch(
            task_id=task.id,
            batch_index=index,
            data_scope={"metrics": list(batch_metrics.keys())},
            status="pending",
            estimated_input_tokens=estimated,
            batch_payload=batch_metrics,
        )
        db.add(row)
        batch_rows.append(row)

    task.total_batches = len(batch_rows)
    task.pending_batches = len(batch_rows)
    task.estimated_total_input_tokens = estimated_total
    db.commit()
    for row in batch_rows:
        db.refresh(row)

    task.status = "processing"
    task.current_step = "Analyzing health data"
    task.progress_message = "AI is analyzing your health data."
    task.progress_percentage = 20
    db.commit()

    for row in batch_rows:
        row.status = "processing"
        task.processing_batches = 1
        task.pending_batches = max(0, task.pending_batches - 1)
        db.commit()

        user_prompt = f"Input:\n{json.dumps(row.batch_payload, default=str)}"
        try:
            analysis, usage = ai_client.generate_json(
                _BATCH_SYSTEM_PROMPT.format(language=task.language), user_prompt
            )
        except Exception as e:  # noqa: BLE001 - any OpenAI/network/parse failure aborts the task
            row.status = "failed"
            row.error_message = str(e)
            task.failed_batches += 1
            task.processing_batches = 0
            db.commit()
            _mark_failed(db, task, "OPENAI_REQUEST_FAILED", str(e), failed_step="analyze_batches")
            return

        row.status = "completed"
        row.batch_analysis = analysis
        row.actual_input_tokens = usage["prompt_tokens"]
        row.actual_output_tokens = usage["completion_tokens"]
        row.completed_at = _now()

        task.completed_batches += 1
        task.processing_batches = 0
        task.actual_total_input_tokens += usage["prompt_tokens"]
        task.actual_total_output_tokens += usage["completion_tokens"]
        task.progress_percentage = 20 + int(60 * task.completed_batches / task.total_batches)
        db.commit()

    task.status = "finalizing"
    task.current_step = "Generating final report"
    task.progress_message = "Merging batch analysis into the final report."
    task.progress_percentage = 90
    db.commit()

    batch_analyses = [{"batch_index": row.batch_index, **(row.batch_analysis or {})} for row in batch_rows]
    abnormal_points = [p for row in batch_rows for p in (row.batch_analysis or {}).get("abnormal_points", [])]
    risk_signals = [r for row in batch_rows for r in (row.batch_analysis or {}).get("risk_signals", [])]
    missing_data = [
        {"batch_index": row.batch_index, **(row.batch_analysis or {}).get("data_quality", {})}
        for row in batch_rows
        if ((row.batch_analysis or {}).get("data_quality") or {}).get("status") != "sufficient"
    ]

    final_input = {
        "report_type": task.report_type,
        "device_id": task.device_id,
        "date_range": _date_range(task.report_type, health_data),
        "overall_status": health_data["overall_status"],
        "summary": health_data["summary"],
        "batch_analyses": batch_analyses,
        "abnormal_points": abnormal_points,
        "risk_signals": risk_signals,
        "missing_data": missing_data,
        "token_usage_so_far": {
            "estimated_total_input_tokens": task.estimated_total_input_tokens,
            "actual_total_input_tokens": task.actual_total_input_tokens,
            "actual_total_output_tokens": task.actual_total_output_tokens,
        },
    }

    final_user_prompt = f"Input:\n{json.dumps(final_input, default=str)}"
    try:
        ai_report, final_usage = ai_client.generate_json(
            _FINAL_SYSTEM_PROMPT.format(language=task.language), final_user_prompt
        )
    except Exception as e:  # noqa: BLE001
        _mark_failed(db, task, "OPENAI_REQUEST_FAILED", str(e), failed_step="generate_final_report")
        return

    task.actual_total_input_tokens += final_usage["prompt_tokens"]
    task.actual_total_output_tokens += final_usage["completion_tokens"]

    now = _now()
    result = ReportResult(
        report_task_id=task.report_task_id,
        device_id=task.device_id,
        report_type=task.report_type,
        date=task.date,
        date_range=_date_range(task.report_type, health_data),
        overall_status=health_data["overall_status"],
        summary=health_data["summary"],
        ai_report=ai_report,
        token_usage={
            "estimated_total_input_tokens": task.estimated_total_input_tokens,
            "actual_total_input_tokens": task.actual_total_input_tokens,
            "actual_total_output_tokens": task.actual_total_output_tokens,
            "final_report_input_tokens": final_usage["prompt_tokens"],
            "final_report_output_tokens": final_usage["completion_tokens"],
        },
        created_at=task.created_at,
        completed_at=now,
    )
    db.add(result)
    db.flush()

    task.status = "completed"
    task.progress_percentage = 100
    task.current_step = "Completed"
    task.progress_message = "AI health report is ready."
    task.result_id = result.id
    task.completed_at = now
    db.add(task)
    db.commit()
