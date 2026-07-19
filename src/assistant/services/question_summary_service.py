import json
import os
from datetime import datetime, timedelta, timezone
from pathlib import Path

from sqlalchemy.orm import Session

from src.assistant.models.question_summary_model import QuestionSummaryRecord
from src.assistant.services.errors import AssistantError
from src.core import ai_client, files
from src.core.logging import logger
from src.device.models.device_model import DeviceRecord
from src.device.models.health_model import HealthRecord
from src.device.models.sleep_model import SleepRecord

QUESTION_SUMMARY_MAX_TOKENS = int(os.getenv("ASSISTANT_QUESTION_MAX_TOKENS", 2000))
MAX_MESSAGE_LENGTH = 500
LOOKBACK_DAYS = 7

# No per-device timezone is stored anywhere in this codebase — matches the same +08:00
# convention data_summary_service used to apply for the (now-removed) analysis module.
REPORT_TZ = timezone(timedelta(hours=8))

_PROMPT_RULES = (Path(__file__).parent / "question_prompt.md").read_text(encoding="utf-8")
_SYSTEM_PROMPT = f"""{_PROMPT_RULES}

Return a single JSON object as described above."""

_INSUFFICIENT_DATA_MESSAGE = {"en": "Not enough data to analyze this question.", "zh": "資料不足無法分析"}


def _validate(mac_address: str | None, previous_response_id: str | None) -> tuple[str | None, str | None]:
    mac_address = mac_address.strip() if mac_address and mac_address.strip() else None
    previous_response_id = (
        previous_response_id.strip() if previous_response_id and previous_response_id.strip() else None
    )
    return mac_address, previous_response_id


def _require_question(message: str | None, has_image: bool) -> None:
    if (not message or not message.strip()) and not has_image:
        raise AssistantError(400, "message 與圖片至少需提供一項", code="INVALID_PARAMETER")
    if message and len(message) > MAX_MESSAGE_LENGTH:
        raise AssistantError(400, "message 不可超過 500 字", code="INVALID_PARAMETER")


def _week_dates(end_date, days: int) -> list[str]:
    return [(end_date - timedelta(days=i)).isoformat() for i in range(days - 1, -1, -1)]


def _query_device_week(db: Session, mac_address: str) -> dict:
    """Queries this device's own trailing-7-day sleep_records/health_records rows (raw, not
    pre-aggregated — see question_prompt.md's `deviceData` field glossary for how the AI is
    expected to read these) so the first turn of a device-bound conversation has real context
    to answer from."""
    device = db.query(DeviceRecord).filter(DeviceRecord.mac_address == mac_address).first()
    if device is None:
        raise AssistantError(404, "找不到指定設備", code="DEVICE_NOT_FOUND")

    end_date = datetime.now(REPORT_TZ).date()
    dates = _week_dates(end_date, LOOKBACK_DAYS)

    sleep_rows = (
        db.query(SleepRecord)
        .filter(SleepRecord.device_id == device.id, SleepRecord.date.in_(dates))
        .all()
    )
    health_rows = (
        db.query(HealthRecord)
        .filter(HealthRecord.device_id == device.id, HealthRecord.date.in_(dates))
        .all()
    )

    if not sleep_rows and not health_rows:
        raise AssistantError(422, "近 7 天內查無有效資料，無法分析問題", code="INSUFFICIENT_DATA")

    return {
        "period": {"start": dates[0], "end": dates[-1]},
        "sleep": [{"date": r.date, "summary": r.sleep_summary} for r in sleep_rows],
        "health": [{"date": r.date, "data": r.data} for r in health_rows],
    }


def _save_uploaded_image(image_bytes: bytes, content_type: str | None) -> str | None:
    pic_id = files.generate_pic_id()
    return files.save_analysis_image(image_bytes, content_type, pic_id)


def generate_question_summary(
    db: Session,
    mac_address: str | None,
    previous_response_id: str | None,
    message: str | None,
    image_bytes: bytes | None,
    content_type: str | None,
    language: str = "zh",
) -> QuestionSummaryRecord:
    """Classifies the user's free-text (and/or image) question into one of 5 categories and
    answers it, branching on whether the user currently has a device bound:

    - macAddress given, no previous_response_id: first turn of a device-bound conversation, so
      this device's own trailing-7-day sleep/health tables are queried fresh (see
      _query_device_week) and folded into this same call's input as `deviceData`.
    - macAddress given, with previous_response_id: chains from an earlier /assistant/question
      turn in the same device-bound conversation without re-querying the database.
    - No macAddress: the user has no device bound at all; answered directly per
      question_prompt.md's no-device rules, optionally chained via previous_response_id to an
      earlier turn of this same no-device conversation.
    """
    mac_address, previous_response_id = _validate(mac_address, previous_response_id)
    _require_question(message, has_image=bool(image_bytes))

    user_question = (message or "").strip()

    device_data = None
    if mac_address and not previous_response_id:
        device_data = _query_device_week(db, mac_address)

    input_text = f"userQuestion: {user_question or '[Image only]'}"
    if device_data is not None:
        input_text += f"\ndeviceData: {json.dumps(device_data, default=str, ensure_ascii=False)}"

    try:
        prompt = ai_client.with_language(_SYSTEM_PROMPT, language)
        result, response_id, _usage = ai_client.generate_json_response(
            prompt,
            input_text,
            previous_response_id,
            image_bytes=image_bytes,
            mime_type=content_type,
            max_output_tokens=QUESTION_SUMMARY_MAX_TOKENS,
        )
    except Exception as e:  # noqa: BLE001
        logger.exception("AI question summary generation failed")
        raise AssistantError(502, "用戶問題分析生成失敗", code="SUMMARY_GENERATION_FAILED") from e

    image_path = _save_uploaded_image(image_bytes, content_type) if image_bytes else None

    if result.get("inScope", True):
        category = result.get("category") or None
        intent = result.get("intent") or None
        confidence = result.get("confidence")
        response_payload = result.get("response")
        benefits = result.get("benefits") or []
    else:
        category, intent, confidence = None, None, 0.0
        response_payload = _INSUFFICIENT_DATA_MESSAGE.get(language, _INSUFFICIENT_DATA_MESSAGE["en"])
        benefits = []

    record = QuestionSummaryRecord(
        mac_address=mac_address,
        user_question=user_question or "[Image]",
        category=category,
        intent=intent,
        confidence=confidence,
        ai_response={"response": response_payload, "benefits": benefits},
        image_path=image_path,
        previous_response_id=previous_response_id,
        response_id=response_id,
    )
    db.add(record)
    db.commit()
    db.refresh(record)
    return record
