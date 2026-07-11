import json
import os
import uuid
from datetime import datetime, timezone
from pathlib import Path

from sqlalchemy.orm import Session

from src.analysis.models.analysis_model import AnalysisRecord
from src.analysis.models.analysis_pic_model import AnalysisPicRecord
from src.analysis.services.answer_format import SUMMARY_KEYS, dump_summary
from src.analysis.services.errors import AnalysisError
from src.core import ai_client, files
from src.core.logging import logger
from src.device.models.device_model import DeviceRecord
from src.health.services.health_insight_service import get_week_averages

MAX_MESSAGE_LENGTH = 500

# Caps the AI reply length for the chat endpoint specifically (tighter than the shared
# OPENAI_MAX_TOKENS default used by other AI features), so replies stay short and cheap.
HEALTH_CHAT_MAX_TOKENS = int(os.getenv("HEALTH_CHAT_MAX_TOKENS", 300))

# Scope + fatigue/recovery knowledge base shared by the chat endpoint; see that file for
# the allowed-topics definition and the fatigue index / recovery condition tables.
_REPLY_RULES = (Path(__file__).parent / "health_reply_rules.md").read_text(encoding="utf-8")

_OUT_OF_SCOPE_MESSAGE = {
    "en": "The provided data cannot be analyzed for this question.",
    "zh": "提供的資料無法分析此問題。",
}

_REQUEST_SYSTEM_PROMPT = f"""You are a friendly health assistant chatting with a user about their fatigue
status and health metrics. This conversation is continued across turns via the Responses API's
previous_response_id — you already have access to this session's prior turns natively; the input payload
below only carries what changes turn to turn:
- "userQuestion": the user's question, supplied by the frontend as text and/or derived from an attached
  image (an image is first identified separately, then its description is folded into this text).
- "latestData": the user's own average health/sleep/activity metrics over the past 7 days, read by the
  backend from its database (always the freshest data the backend has stored — re-sent every turn since
  it can change between turns even within the same conversation).
- "prevSummary" (optional, only present when the frontend has one): a free-text summary of the
  conversation so far, supplied directly by the frontend.
Reason over userQuestion together with latestData, this session's prior turns, and prevSummary as a
whole — do not answer from userQuestion in isolation — grounded in the reply rules below.

{_REPLY_RULES}

Return a JSON object: {{"inScope": <boolean>, "healthSummary": "<string>", "fatigueSummary": "<string>",
"recoverySummary": "<string>"}}
Rules:
- First judge whether userQuestion falls within the allowed reply scope defined above
  (health metrics or fatigue/recovery status only).
- If out of scope, set "inScope" to false, set "healthSummary" to exactly the fallback sentence
  given above for the response language, and set "fatigueSummary" and "recoverySummary" to "".
- If in scope, set "inScope" to true, and fill in "healthSummary", "fatigueSummary", and
  "recoverySummary" with your reasoning for each aspect (health metrics; fatigue index status per
  section 2; recovery stage/flags per section 3). Leave a field as "" if that aspect is not
  relevant to userQuestion — do not pad an irrelevant field just to fill it in.
- Do not diagnose disease or recommend medication or medical treatment.
- Base the answer only on the provided data; if data is insufficient, state so clearly instead of guessing.
- Keep each field concise (a short paragraph, not a wall of text).
- Use clear, simple, conversational language.
- Return JSON only."""

_PIC_IDENTIFY_SYSTEM_PROMPT = """You are a vision assistant performing a preliminary identification of an
uploaded image (e.g. food, an activity, or a health-related item). Describe what is visible in the image.
Return a JSON object: {"message": "<string>"}
Rules:
- Do not diagnose disease or recommend medication or medical treatment.
- Use clear, simple language.
- Return JSON only."""


def _require_non_empty(value: str | None, error_message: str) -> str:
    if value is None or not value.strip():
        raise AnalysisError(400, error_message)
    return value


def _require_question(message: str | None, has_image: bool) -> None:
    """user_question may arrive as text, an image, or both — but never neither."""
    if (not message or not message.strip()) and not has_image:
        raise AnalysisError(400, "message 與圖片至少需提供一項")
    if message and len(message) > MAX_MESSAGE_LENGTH:
        raise AnalysisError(400, "message 不可超過 500 字")


def _generate_pic_id() -> str:
    return "analysis_pic_" + datetime.now(timezone.utc).strftime("%Y%m%d%H%M%S%f")[:-3]


def _generate_session_id() -> str:
    return "session_" + uuid.uuid4().hex


def _resolve_session_id(session_id: str | None) -> str:
    """Continues the frontend-echoed session_id when present so a conversation's turns
    stay grouped under one id; mints a fresh one only when the frontend has none yet
    (i.e. this is the first turn)."""
    return session_id.strip() if session_id and session_id.strip() else _generate_session_id()


def _generate_summary(
    system_prompt: str,
    payload: dict,
    language: str,
    previous_response_id: str | None,
    max_tokens: int | None = None,
) -> tuple[dict, str | None]:
    try:
        prompt = ai_client.with_language(system_prompt, language)
        result, response_id, _usage = ai_client.generate_json_response(
            prompt, f"Input:\n{json.dumps(payload, default=str)}", previous_response_id, max_output_tokens=max_tokens
        )
        if not result.get("inScope", True):
            fallback = _OUT_OF_SCOPE_MESSAGE.get(language, _OUT_OF_SCOPE_MESSAGE["en"])
            return {"healthSummary": fallback, "fatigueSummary": "", "recoverySummary": ""}, response_id
        return {key: str(result.get(key) or "") for key in SUMMARY_KEYS}, response_id
    except Exception as e:  # noqa: BLE001
        logger.exception("AI analysis generation failed")
        return {
            "healthSummary": f"Unable to generate analysis: {e}", "fatigueSummary": "", "recoverySummary": "",
        }, None


def _identify_image(
    image_bytes: bytes, content_type: str | None, language: str, prompt_text: str | None = None
) -> str:
    prompt_text = prompt_text or (
        "請描述這張圖片的內容。" if language == "zh" else "Please describe what is visible in this image."
    )
    try:
        result, _usage = ai_client.generate_json_with_image(
            ai_client.with_language(_PIC_IDENTIFY_SYSTEM_PROMPT, language),
            prompt_text,
            image_bytes,
            content_type or "image/jpeg",
        )
        return result.get("message", "")
    except Exception as e:  # noqa: BLE001
        logger.exception("AI image identification failed")
        return f"Unable to identify image: {e}"


def _resolve_user_question(
    db: Session,
    mac_address: str,
    session_id: str,
    message: str | None,
    image_bytes: bytes | None,
    content_type: str | None,
    language: str,
) -> tuple[str, str | None]:
    """Builds the combined user_question text: the frontend's text message, an attached
    image's AI-identified description, or both. When an image is attached it is persisted
    for audit history, and pic_id is returned for the AnalysisRecord this turn produces."""
    parts = []
    text = message.strip() if message and message.strip() else None
    if text:
        parts.append(text)

    pic_id = None
    if image_bytes:
        pic_message = _identify_image(image_bytes, content_type, language)
        pic_id = _generate_pic_id()
        image_path = files.save_analysis_image(image_bytes, content_type, pic_id)
        db.add(AnalysisPicRecord(
            mac_address=mac_address,
            session_id=session_id,
            pic_id=pic_id,
            pic_message=pic_message,
            image_path=image_path,
        ))
        db.commit()
        parts.append(f"[Image]: {pic_message}")

    return "\n".join(parts), pic_id


def _latest_response_id(db: Session, mac_address: str, session_id: str) -> str | None:
    """The OpenAI Responses API id of this session's most recent turn, passed back as
    previous_response_id so OpenAI resumes the conversation server-side instead of this service
    replaying history into the prompt. None for a brand-new session, or if the latest turn
    predates the openai_response_id column, or if that turn's AI call itself failed."""
    record = (
        db.query(AnalysisRecord)
        .filter(AnalysisRecord.mac_address == mac_address, AnalysisRecord.session_id == session_id)
        .order_by(AnalysisRecord.record_datetime.desc())
        .first()
    )
    return record.openai_response_id if record else None


def _record_analysis(
    db: Session,
    mac_address: str,
    session_id: str,
    user_question: str,
    system_answer: dict,
    pic_id: str | None = None,
    openai_response_id: str | None = None,
) -> None:
    record_datetime = datetime.now(timezone.utc)
    existing = db.query(AnalysisRecord).filter(
        AnalysisRecord.mac_address == mac_address,
        AnalysisRecord.record_datetime == record_datetime,
    ).first()
    if existing is not None:
        return
    db.add(AnalysisRecord(
        mac_address=mac_address,
        session_id=session_id,
        record_datetime=record_datetime,
        user_question=user_question,
        # system_answer is a Text column; the structured summary is JSON-encoded so it round-trips
        # through load_stored_summary (see answer_format.py) for compact-summary.
        system_answer=dump_summary(system_answer),
        pic_id=pic_id,
        openai_response_id=openai_response_id,
    ))
    db.commit()


def _build_ai_payload(db: Session, device: DeviceRecord, user_question: str, prev_summary: str | None) -> dict:
    payload = {
        "userQuestion": user_question,
        "latestData": get_week_averages(db, device.id),
    }
    if prev_summary and prev_summary.strip():
        payload["prevSummary"] = prev_summary.strip()
    return payload


def handle_request(
    db: Session,
    mac_address: str,
    session_id: str | None,
    message: str | None,
    prev_summary: str | None,
    image_bytes: bytes | None,
    content_type: str | None,
    language: str = "en",
) -> tuple[dict, str]:
    mac_address = _require_non_empty(mac_address, "macAddress 不可為空")
    _require_question(message, has_image=bool(image_bytes))

    device = db.query(DeviceRecord).filter(DeviceRecord.mac_address == mac_address).first()
    if device is None:
        raise AnalysisError(404, "找不到對應設備")

    session_id = _resolve_session_id(session_id)
    user_question, pic_id = _resolve_user_question(
        db, mac_address, session_id, message, image_bytes, content_type, language
    )

    previous_response_id = _latest_response_id(db, mac_address, session_id)
    payload = _build_ai_payload(db, device, user_question, prev_summary)
    summary, response_id = _generate_summary(
        _REQUEST_SYSTEM_PROMPT, payload, language, previous_response_id, max_tokens=HEALTH_CHAT_MAX_TOKENS
    )

    _record_analysis(db, mac_address, session_id, user_question, summary, pic_id=pic_id, openai_response_id=response_id)
    return summary, session_id


def build_prompt_preview(
    db: Session,
    mac_address: str,
    session_id: str | None,
    message: str,
    prev_summary: str | None,
    language: str = "en",
) -> dict:
    """Debug-only: assembles the exact system prompt + user payload /request would send to the
    AI, without calling OpenAI and without writing anything to the database (no AnalysisRecord,
    no pic upload). Image attachments aren't supported here since identifying one requires an
    OpenAI vision call, which this endpoint must never make."""
    mac_address = _require_non_empty(mac_address, "macAddress 不可為空")
    message = _require_non_empty(message, "message 不可為空")

    device = db.query(DeviceRecord).filter(DeviceRecord.mac_address == mac_address).first()
    if device is None:
        raise AnalysisError(404, "找不到對應設備")

    session_id = _resolve_session_id(session_id)
    user_question = message.strip()
    previous_response_id = _latest_response_id(db, mac_address, session_id)

    payload = _build_ai_payload(db, device, user_question, prev_summary)
    system_prompt = ai_client.with_language(_REQUEST_SYSTEM_PROMPT, language)

    return {
        "session_id": session_id,
        "previousResponseId": previous_response_id,
        "systemPrompt": system_prompt,
        "payload": payload,
        "userPrompt": f"Input:\n{json.dumps(payload, default=str)}",
    }
