import json
from datetime import datetime, timezone

from sqlalchemy.orm import Session

from src.analysis.models.analysis_model import AnalysisRecord
from src.analysis.models.analysis_pic_model import AnalysisPicRecord
from src.analysis.services.errors import AnalysisError
from src.core import ai_client, files
from src.core.logging import logger
from src.device.models.device_model import DeviceRecord
from src.summary.models.summary_model import DailyHealthSummaryRecord

MAX_MESSAGE_LENGTH = 500

_REQUEST_SYSTEM_PROMPT = """You are a friendly health assistant chatting with a user about their daily
health summary (sleep, activity, vital signs). Answer the user's question using the provided summary data.
Return a JSON object: {"message": "<string>"}
Rules:
- Do not diagnose disease or recommend medication or medical treatment.
- Base the answer only on the provided data; if data is insufficient, state so clearly.
- Use clear, simple, conversational language.
- Return JSON only."""

_KEEP_REQUEST_SYSTEM_PROMPT = """You are a friendly health assistant continuing a conversation with a user
about their daily health. Use the previous answer as context and respond to the user's follow-up question.
Return a JSON object: {"message": "<string>"}
Rules:
- Do not diagnose disease or recommend medication or medical treatment.
- Use clear, simple, conversational language.
- Return JSON only."""

_PIC_IDENTIFY_SYSTEM_PROMPT = """You are a vision assistant performing a preliminary identification of an
uploaded image (e.g. food, an activity, or a health-related item). Describe what is visible in the image.
Return a JSON object: {"message": "<string>"}
Rules:
- Do not diagnose disease or recommend medication or medical treatment.
- Use clear, simple language.
- Return JSON only."""

_PIC_ANSWER_SYSTEM_PROMPT = """You are a friendly health assistant. You will receive a preliminary image
identification result and the user's daily health summary. Combine both to give a helpful, contextual
health-related answer about the image. Return a JSON object: {"message": "<string>"}
Rules:
- Do not diagnose disease or recommend medication or medical treatment.
- Base the answer only on the provided data; if data is insufficient, state so clearly.
- Use clear, simple, conversational language.
- Return JSON only."""


def _require_non_empty(value: str | None, error_message: str) -> str:
    if value is None or not value.strip():
        raise AnalysisError(400, error_message)
    return value


def _require_message(message: str | None) -> str:
    message = _require_non_empty(message, "message 不可為空")
    if len(message) > MAX_MESSAGE_LENGTH:
        raise AnalysisError(400, "message 不可超過 500 字")
    return message


def _generate_pic_id() -> str:
    return "analysis_pic_" + datetime.now(timezone.utc).strftime("%Y%m%d%H%M%S%f")[:-3]


def _generate_answer(system_prompt: str, payload: dict, language: str) -> str:
    try:
        prompt = ai_client.with_language(system_prompt, language)
        result, _usage = ai_client.generate_json(prompt, f"Input:\n{json.dumps(payload, default=str)}")
        return result.get("message", "")
    except Exception as e:  # noqa: BLE001
        logger.exception("AI analysis generation failed")
        return f"Unable to generate analysis: {e}"


def _summary_context(record: DailyHealthSummaryRecord | None) -> dict:
    if record is None:
        return {}
    return {
        "sleep": {
            "score": record.sleep_score,
            "summary": record.sleep_summary,
            "suggestion": record.sleep_suggestion,
        },
        "activity": {
            "score": record.activity_score,
            "summary": record.activity_summary,
            "suggestion": record.activity_suggestion,
        },
        "health": {
            "score": record.health_score,
            "summary": record.health_summary,
            "suggestion": record.health_suggestion,
        },
        "overall": {
            "score": record.overall_score,
            "summary": record.overall_summary,
            "suggestion": record.overall_suggestion,
        },
    }


def _get_today_summary(db: Session, device_id: int) -> DailyHealthSummaryRecord | None:
    today = datetime.now(timezone.utc).date().isoformat()
    return db.query(DailyHealthSummaryRecord).filter(
        DailyHealthSummaryRecord.device_id == device_id,
        DailyHealthSummaryRecord.date == today,
    ).first()


def _record_analysis(
    db: Session, mac_address: str, user_question: str, system_answer: str, pic_id: str | None = None
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
        record_datetime=record_datetime,
        user_question=user_question,
        system_answer=system_answer,
        pic_id=pic_id,
    ))
    db.commit()


def handle_request(db: Session, mac_address: str, message: str, language: str = "en") -> str:
    mac_address = _require_non_empty(mac_address, "macAddress 不可為空")
    message = _require_message(message)

    device = db.query(DeviceRecord).filter(DeviceRecord.mac_address == mac_address).first()
    if device is None:
        raise AnalysisError(404, "找不到對應設備")

    summary_row = _get_today_summary(db, device.id)
    payload = {"message": message, "summaryData": _summary_context(summary_row)}
    answer = _generate_answer(_REQUEST_SYSTEM_PROMPT, payload, language)

    _record_analysis(db, mac_address, message, answer)
    return answer


def handle_keep_request(
    db: Session, mac_address: str, previous_answer: str, message: str, language: str = "en"
) -> str:
    mac_address = _require_non_empty(mac_address, "macAddress 不可為空")
    previous_answer = _require_non_empty(previous_answer, "previousAnswer 不可為空")
    message = _require_message(message)

    payload = {"previousAnswer": previous_answer, "message": message}
    answer = _generate_answer(_KEEP_REQUEST_SYSTEM_PROMPT, payload, language)

    _record_analysis(db, mac_address, message, answer)
    return answer


def handle_pic_identify(
    db: Session,
    mac_address: str | None,
    image_bytes: bytes,
    content_type: str | None,
    message: str | None,
    language: str = "en",
) -> str:
    mac_address = _require_non_empty(mac_address, "macAddress 不可為空")
    if not image_bytes:
        raise AnalysisError(400, "圖片不可為空")
    if message and len(message) > MAX_MESSAGE_LENGTH:
        raise AnalysisError(400, "message 不可超過 500 字")

    prompt_text = message.strip() if message and message.strip() else "請描述這張圖片的內容。"
    try:
        result, _usage = ai_client.generate_json_with_image(
            ai_client.with_language(_PIC_IDENTIFY_SYSTEM_PROMPT, language),
            prompt_text,
            image_bytes,
            content_type or "image/jpeg",
        )
        pic_message = result.get("message", "")
    except Exception as e:  # noqa: BLE001
        logger.exception("AI image identification failed")
        pic_message = f"Unable to identify image: {e}"

    pic_id = _generate_pic_id()
    image_path = files.save_analysis_image(image_bytes, content_type, pic_id)

    db.add(AnalysisPicRecord(
        mac_address=mac_address,
        pic_id=pic_id,
        pic_message=pic_message,
        image_path=image_path,
    ))
    db.commit()
    return pic_id


def handle_pic_answer(db: Session, mac_address: str, pic_id: str, language: str = "en") -> str:
    mac_address = _require_non_empty(mac_address, "macAddress 不可為空")
    pic_id = _require_non_empty(pic_id, "pic_id 不可為空")

    pic_row = db.query(AnalysisPicRecord).filter(
        AnalysisPicRecord.mac_address == mac_address,
        AnalysisPicRecord.pic_id == pic_id,
    ).first()
    if pic_row is None:
        raise AnalysisError(404, "找不到對應的圖片分析結果")
    if not pic_row.pic_message:
        raise AnalysisError(409, "圖片分析尚未完成")

    device = db.query(DeviceRecord).filter(DeviceRecord.mac_address == mac_address).first()
    summary_row = _get_today_summary(db, device.id) if device else None

    payload = {"summaryData": _summary_context(summary_row), "picMessage": pic_row.pic_message}
    answer = _generate_answer(_PIC_ANSWER_SYSTEM_PROMPT, payload, language)

    _record_analysis(db, mac_address, "圖片健康分析請求", answer, pic_id=pic_id)
    return answer
