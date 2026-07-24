import json
import uuid
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

from sqlalchemy.orm import Session

from src.core import ai_client
from src.core.database import SessionLocal
from src.core.logging import logger
from src.device.models.activity_model import ActivityRecord
from src.device.models.device_model import DeviceRecord
from src.device.models.health_model import HealthRecord
from src.device.models.sleep_model import SleepRecord
from src.health_report.models.health_report_model import HealthReportRecord
from src.health_report.schemas.health_report_schema import HealthReportCreateRequest
from src.health_report.services import report_stats_service
from src.health_report.services.errors import HealthReportError

AI_MAX_TOKENS = 2500

_PROMPT_RULES = (Path(__file__).parent / "health_report_prompt.md").read_text(encoding="utf-8")
_SYSTEM_PROMPT = f"""{_PROMPT_RULES}

Return a single JSON object as described above."""

_STAGE_LABELS = {
    "collecting_data": "正在彙整穿戴裝置數據",
    "ai_analysis": "正在產生健康分析與改善建議",
    "completed": "健康摘要已完成",
}

_STATUS_LABELS = {
    "good": "表現良好",
    "normal": "正常",
    "stable": "穩定",
    "improving": "持續改善",
    "attention": "需要留意",
    "abnormal": "異常",
    "insufficient_data": "資料不足",
}


def _new_report_id() -> str:
    return f"rpt_{uuid.uuid4().hex}"


def resolve_device(db: Session, user_id: int) -> DeviceRecord | None:
    """The user's most-recently-synced bound device. v1 doesn't support multi-device selection —
    see plan's "本次不做" list."""
    return (
        db.query(DeviceRecord)
        .filter(DeviceRecord.user_id == user_id)
        .order_by(DeviceRecord.last_sync.desc().nullslast())
        .first()
    )


def create_report(db: Session, user_id: int, body: HealthReportCreateRequest) -> HealthReportRecord:
    device = resolve_device(db, user_id)
    if device is None:
        raise HealthReportError(400, "找不到已綁定的裝置，請先完成裝置綁定", code="NO_DEVICE_BOUND")

    try:
        period = report_stats_service.compute_period(anchor_date=body.date)
    except report_stats_service.InvalidReportDateError as e:
        raise HealthReportError(400, f"無效的日期：{body.date}", code="INVALID_DATE") from e

    record = HealthReportRecord(
        report_id=_new_report_id(),
        user_id=user_id,
        device_id=device.id,
        report_type=body.report_type,
        language=body.language,
        include_ai_analysis=body.include_ai_analysis,
        status="queued",
        progress=0,
        period_start=period["period_start"],
        period_end=period["period_end"],
        comparison_start=period["comparison_start"],
        comparison_end=period["comparison_end"],
    )
    db.add(record)
    db.commit()
    db.refresh(record)
    return record


def get_report_record(db: Session, report_id: str) -> HealthReportRecord | None:
    return db.query(HealthReportRecord).filter(HealthReportRecord.report_id == report_id).first()


def _fetch_records(db: Session, model, device_id: int, dates: list[str]) -> list:
    return db.query(model).filter(model.device_id == device_id, model.date.in_(dates)).all()


def _scores_for_window(
    db: Session, device: DeviceRecord, period_start: str, period_end: str, comparison_start: str, comparison_end: str
) -> dict:
    """Runs the same deterministic scoring pass as the main report, but shifted one week earlier,
    purely to get comparable overall/category scores for "vs last report" — see overall.change and
    category_summary[*].change below. Cheap (pure Python + one extra date-range query), no AI call."""
    all_dates = report_stats_service.date_range(period_start, period_end) + report_stats_service.date_range(
        comparison_start, comparison_end
    )
    summary = report_stats_service.compute_summary(
        device,
        _fetch_records(db, SleepRecord, device.id, all_dates),
        _fetch_records(db, HealthRecord, device.id, all_dates),
        _fetch_records(db, ActivityRecord, device.id, all_dates),
        {
            "period_start": period_start,
            "period_end": period_end,
            "comparison_start": comparison_start,
            "comparison_end": comparison_end,
        },
    )
    return {
        "overall": summary["overall"]["score"],
        **{category: values["score"] for category, values in summary["category_summary"].items()},
    }


def _score_direction(current: float | None, previous: float | None) -> str:
    if current is None or previous is None:
        return "stable"
    diff = current - previous
    if abs(diff) < 1:
        return "stable"
    return "up" if diff > 0 else "down"


def _overall_change(current_score: float | None, previous_score: float | None) -> dict:
    if current_score is None or previous_score is None:
        return {"value": None, "unit": "point", "direction": "stable", "comparison_label": None}
    value = round(current_score - previous_score)
    direction = "stable" if value == 0 else ("up" if value > 0 else "down")
    verb = "持平" if value == 0 else ("上升" if value > 0 else "下降")
    return {
        "value": value,
        "unit": "point",
        "direction": direction,
        "comparison_label": f"較前 7 天{verb}{abs(value)} 分" if value != 0 else "較前 7 天持平",
    }


def _default_ai_fallback(overall_status: str) -> dict:
    """Used when include_ai_analysis=false — keeps the response shape stable without inventing
    AI-authored narrative text."""
    return {
        "overall_title": _STATUS_LABELS.get(overall_status, ""),
        "overall_summary": "",
        "category_narratives": {"sleep": "", "health": "", "activity": ""},
    }


def run_generation(report_id: str) -> None:
    """Entry point for FastAPI BackgroundTasks (see health_report/api.py). Runs after the HTTP
    response for POST /health-reports has already been sent, so it cannot reuse the
    request-scoped SessionDep — it opens its own session for the whole job."""
    db = SessionLocal()
    try:
        record = get_report_record(db, report_id)
        if record is None:
            logger.error("health report %s vanished before generation started", report_id)
            return

        record.status = "processing"
        record.stage = "collecting_data"
        record.progress = 20
        db.commit()

        device = db.query(DeviceRecord).filter(DeviceRecord.id == record.device_id).first()
        if device is None:
            raise HealthReportError(400, "裝置已不存在", code="NO_DEVICE_BOUND")

        period = {
            "period_start": record.period_start,
            "period_end": record.period_end,
            "comparison_start": record.comparison_start,
            "comparison_end": record.comparison_end,
        }
        all_dates = report_stats_service.date_range(
            period["period_start"], period["period_end"]
        ) + report_stats_service.date_range(period["comparison_start"], period["comparison_end"])

        summary = report_stats_service.compute_summary(
            device,
            _fetch_records(db, SleepRecord, device.id, all_dates),
            _fetch_records(db, HealthRecord, device.id, all_dates),
            _fetch_records(db, ActivityRecord, device.id, all_dates),
            period,
        )

        pre_comparison_end = date.fromisoformat(period["comparison_start"]) - timedelta(days=1)
        pre_comparison_start = pre_comparison_end - timedelta(days=report_stats_service.PERIOD_DAYS - 1)
        previous_scores = _scores_for_window(
            db,
            device,
            period["comparison_start"],
            period["comparison_end"],
            pre_comparison_start.isoformat(),
            pre_comparison_end.isoformat(),
        )

        record.stage = "ai_analysis"
        record.progress = 60
        db.commit()

        if record.include_ai_analysis:
            evidence_payload = {
                "period": summary["period"],
                "comparison_period": summary["comparison_period"],
                "data_quality": summary["data_quality"],
                "overall": summary["overall"],
                "category_summary": summary["category_summary"],
                "priority_items": summary["priority_items"],
                "sleep_summary": summary["sleep_summary"],
                "health_summary": summary["health_summary"],
                "activity_summary": summary["activity_summary"],
            }
            try:
                prompt = ai_client.with_language(_SYSTEM_PROMPT, "zh" if record.language.startswith("zh") else "en")
                ai_json, _response_id, _usage = ai_client.generate_json_response(
                    prompt,
                    json.dumps(evidence_payload, ensure_ascii=False, default=str),
                    max_output_tokens=AI_MAX_TOKENS,
                )
            except Exception as e:  # noqa: BLE001
                logger.exception("AI health report analysis failed for %s", report_id)
                record.status = "failed"
                record.error_code = "REPORT_GENERATION_FAILED"
                record.error_message = f"AI 分析產生失敗：{e}"
                db.commit()
                return
            ai_analysis = {
                "model": ai_client.OPENAI_MODEL,
                "generated_at": datetime.now(timezone.utc).isoformat(),
                "key_findings": ai_json.get("key_findings", []),
                "potential_risks": ai_json.get("potential_risks", []),
                "recommendations": ai_json.get("recommendations", []),
                "questions_for_user": ai_json.get("questions_for_user", []),
                "safety_notice": ai_json.get("safety_notice"),
            }
            overall_title = ai_json.get("overall_title", "")
            overall_summary = ai_json.get("overall_summary", "")
            category_narratives = ai_json.get("category_narratives", {})
        else:
            ai_analysis = None
            fallback = _default_ai_fallback(summary["overall"]["status"])
            overall_title = fallback["overall_title"]
            overall_summary = fallback["overall_summary"]
            category_narratives = fallback["category_narratives"]

        completed_at = datetime.now(timezone.utc)
        payload = {
            "report_id": record.report_id,
            "user_id": record.user_id,
            "report_type": record.report_type,
            "status": "completed",
            "language": record.language,
            "period": summary["period"],
            "comparison_period": summary["comparison_period"],
            "data_quality": summary["data_quality"],
            "overall": {
                **summary["overall"],
                "status_label": _STATUS_LABELS.get(summary["overall"]["status"], summary["overall"]["status"]),
                "change": _overall_change(summary["overall"]["score"], previous_scores.get("overall")),
                "title": overall_title,
                "summary": overall_summary,
            },
            "priority_items": summary["priority_items"],
            "category_summary": {
                category: {
                    **values,
                    "change": (
                        None
                        if values["score"] is None or previous_scores.get(category) is None
                        else round(values["score"] - previous_scores[category])
                    ),
                    "change_direction": _score_direction(values["score"], previous_scores.get(category)),
                    "summary": category_narratives.get(category, ""),
                }
                for category, values in summary["category_summary"].items()
            },
            "sleep_summary": summary["sleep_summary"],
            "health_summary": summary["health_summary"],
            "activity_summary": summary["activity_summary"],
            "ai_analysis": ai_analysis,
            "created_at": record.created_at.isoformat(),
            "completed_at": completed_at.isoformat(),
        }

        record.payload = payload
        record.status = "completed"
        record.stage = "completed"
        record.progress = 100
        record.completed_at = completed_at
        db.commit()
    except Exception as e:  # noqa: BLE001
        logger.exception("Health report generation failed for %s", report_id)
        db.rollback()
        record = get_report_record(db, report_id)
        if record is not None:
            record.status = "failed"
            record.error_code = getattr(e, "code", None) or "REPORT_GENERATION_FAILED"
            record.error_message = str(e)
            db.commit()
    finally:
        db.close()


def status_payload(record: HealthReportRecord) -> dict:
    if record.status == "failed":
        return {
            "success": False,
            "error": {
                "code": record.error_code or "REPORT_GENERATION_FAILED",
                "message": record.error_message or "健康摘要產生失敗，請稍後重新嘗試。",
                "retryable": True,
            },
        }
    data = {
        "report_id": record.report_id,
        "status": record.status,
        "stage": record.stage,
        "stage_label": _STAGE_LABELS.get(record.stage, record.stage),
        "progress": record.progress,
    }
    if record.status == "completed":
        data["result_available"] = True
    else:
        data["poll_interval_seconds"] = 10
    return {"success": True, "data": data}
