import os
from pathlib import Path

from sqlalchemy.orm import Session

from src.assistant.models.question_summary_model import QuestionSummaryRecord
from src.assistant.services.errors import AssistantError
from src.core import ai_client, files
from src.core.logging import logger

QUESTION_SUMMARY_MAX_TOKENS = int(os.getenv("ASSISTANT_QUESTION_MAX_TOKENS", 2000))
MAX_MESSAGE_LENGTH = 500

_PROMPT_RULES = (Path(__file__).parent / "question_prompt.md").read_text(encoding="utf-8")
_SYSTEM_PROMPT = f"""{_PROMPT_RULES}

Return a single JSON object as described above."""

_INSUFFICIENT_DATA_MESSAGE = {"en": "Not enough data to analyze this question.", "zh": "資料不足無法分析"}


def _validate(mac_address: str | None, previous_response_id: str | None) -> tuple[str, str]:
    if not mac_address or not mac_address.strip():
        raise AssistantError(400, "macAddress 不可為空", code="INVALID_PARAMETER")
    if not previous_response_id or not previous_response_id.strip():
        raise AssistantError(
            400, "responseId 不可為空，請先呼叫 /assistant/trend", code="INVALID_PARAMETER"
        )
    return mac_address.strip(), previous_response_id.strip()


def _require_question(message: str | None, has_image: bool) -> None:
    if (not message or not message.strip()) and not has_image:
        raise AssistantError(400, "message 與圖片至少需提供一項", code="INVALID_PARAMETER")
    if message and len(message) > MAX_MESSAGE_LENGTH:
        raise AssistantError(400, "message 不可超過 500 字", code="INVALID_PARAMETER")


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
    """Stage 3 of the assistant flow: classifies the user's free-text (and/or image) question
    into one of 5 categories and answers it, chained from /assistant/trend so the AI already has
    this user's profile/level and 7-day trend in context server-side."""
    mac_address, previous_response_id = _validate(mac_address, previous_response_id)
    _require_question(message, has_image=bool(image_bytes))

    user_question = (message or "").strip()

    try:
        prompt = ai_client.with_language(_SYSTEM_PROMPT, language)
        result, response_id, _usage = ai_client.generate_json_response(
            prompt,
            f"userQuestion: {user_question or '[Image only]'}",
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
