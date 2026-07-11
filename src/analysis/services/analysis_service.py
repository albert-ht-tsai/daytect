import json
import os
import uuid
from datetime import datetime, timezone
from pathlib import Path

from sqlalchemy.orm import Session

from src.analysis.models.analysis_model import AnalysisRecord
from src.analysis.models.analysis_pic_model import AnalysisPicRecord
from src.analysis.schemas.analysis_schema import LatestSummary
from src.analysis.services.answer_format import as_bullet_list, dump_answer
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
status and health metrics. The input payload is assembled as follows:
- "userQuestion": the user's question, supplied by the frontend as text and/or derived from an attached
  image (an image is first identified separately, then its description is folded into this text).
- "latestData": the user's own average health/sleep/activity metrics over the past 7 days, read by the
  backend from its database.
- "latestSummary": the user's most recent health snapshot supplied directly by the frontend (e.g. from a
  just-completed manual ECG detection), which may be more current than latestData.
Answer using only userQuestion/latestData/latestSummary, grounded in the reply rules below.

{_REPLY_RULES}

Return a JSON object: {{"inScope": <boolean>, "message": ["<string>", ...]}}
Rules:
- First judge whether userQuestion falls within the allowed reply scope defined above
  (health metrics or fatigue/recovery status only).
- If out of scope, set "inScope" to false and set "message" to a single-element array
  containing exactly the fallback sentence given above for the response language.
- If in scope, set "inScope" to true and set "message" to an array of bullet points, one
  element per relevant metric/key used to answer (e.g. heart rate, HRV, sleep quality,
  fatigue level), each formatted as "<key>: <finding>". Do not merge multiple keys into
  one bullet, and do not add a bullet for a key you did not actually use.
- Do not diagnose disease or recommend medication or medical treatment.
- Base the answer only on the provided data; if data is insufficient, state so clearly instead of guessing.
- Keep it to at most 6 bullets.
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


def _generate_answer(
    system_prompt: str, payload: dict, language: str, max_tokens: int | None = None
) -> list[str]:
    try:
        prompt = ai_client.with_language(system_prompt, language)
        result, _usage = ai_client.generate_json(
            prompt, f"Input:\n{json.dumps(payload, default=str)}", max_tokens=max_tokens
        )
        if not result.get("inScope", True):
            return [_OUT_OF_SCOPE_MESSAGE.get(language, _OUT_OF_SCOPE_MESSAGE["en"])]
        return as_bullet_list(result.get("message"))
    except Exception as e:  # noqa: BLE001
        logger.exception("AI analysis generation failed")
        return [f"Unable to generate analysis: {e}"]


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


def _latest_summary_context(latest_summary: LatestSummary | None) -> dict:
    if latest_summary is None:
        return {}
    # ppg is a raw signal, not meaningful to an LLM and expensive in tokens; only its
    # presence/size is surfaced, the samples themselves are never sent to the AI.
    data = latest_summary.model_dump(exclude={"ppg"}, exclude_none=True)
    if latest_summary.ppg:
        data["ppgSampleCount"] = len(latest_summary.ppg)
    return data


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


def _record_analysis(
    db: Session,
    mac_address: str,
    session_id: str,
    user_question: str,
    system_answer: list[str],
    pic_id: str | None = None,
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
        # system_answer is a Text column; the bullet list is JSON-encoded so it round-trips
        # through load_stored_answer (see answer_format.py) for compact-summary.
        system_answer=dump_answer(system_answer),
        pic_id=pic_id,
    ))
    db.commit()


def handle_request(
    db: Session,
    mac_address: str,
    session_id: str | None,
    message: str | None,
    latest_summary: LatestSummary | None,
    image_bytes: bytes | None,
    content_type: str | None,
    language: str = "en",
) -> tuple[list[str], str]:
    mac_address = _require_non_empty(mac_address, "macAddress 不可為空")
    _require_question(message, has_image=bool(image_bytes))

    device = db.query(DeviceRecord).filter(DeviceRecord.mac_address == mac_address).first()
    if device is None:
        raise AnalysisError(404, "找不到對應設備")

    session_id = _resolve_session_id(session_id)
    user_question, pic_id = _resolve_user_question(
        db, mac_address, session_id, message, image_bytes, content_type, language
    )

    payload = {
        "userQuestion": user_question,
        "latestData": get_week_averages(db, device.id),
        "latestSummary": _latest_summary_context(latest_summary),
    }
    answer = _generate_answer(_REQUEST_SYSTEM_PROMPT, payload, language, max_tokens=HEALTH_CHAT_MAX_TOKENS)

    _record_analysis(db, mac_address, session_id, user_question, answer, pic_id=pic_id)
    return answer, session_id
