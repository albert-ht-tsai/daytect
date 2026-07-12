from pathlib import Path

from sqlalchemy.orm import Session

from src.analysis.models.analysis_pic_model import AnalysisPicRecord
from src.analysis.models.health_summary_model import HealthSummaryRecord
from src.analysis.services.errors import AnalysisError
from src.core import ai_client, files
from src.core.logging import logger

PROMPT_VERSION = "health_summary_v1"

_PROMPT_RULES = (Path(__file__).parent / "health_summary_prompt.md").read_text(encoding="utf-8")

_SYSTEM_PROMPT = f"""{_PROMPT_RULES}

Return a single JSON object containing the health summary described above (title, the user's
question, a direct answer, key findings drawn only from the prior turn's data, possible
relationships, recommendations, limitations, and a disclaimer). The exact field names are up to
you; the content and rules above are not."""


def _validate(mac_address: str | None, user_input: str | None, previous_response_id: str | None) -> tuple[str, str, str]:
    if not mac_address or not mac_address.strip():
        raise AnalysisError(400, "macAddress 不可為空", code="INVALID_PARAMETER")
    if not user_input or not user_input.strip():
        raise AnalysisError(400, "userInput 不可為空", code="INVALID_PARAMETER")
    if not previous_response_id or not previous_response_id.strip():
        raise AnalysisError(400, "previousResponseId 不可為空", code="INVALID_PARAMETER")
    return mac_address.strip(), user_input.strip(), previous_response_id.strip()


def _save_uploaded_image(db: Session, mac_address: str, image_bytes: bytes, content_type: str | None) -> str:
    pic_id = files.generate_pic_id()
    image_path = files.save_analysis_image(image_bytes, content_type, pic_id)
    db.add(AnalysisPicRecord(mac_address=mac_address, pic_id=pic_id, image_path=image_path))
    db.commit()
    return pic_id


def generate_health_summary(
    db: Session,
    mac_address: str | None,
    user_input: str | None,
    previous_response_id: str | None,
    image_bytes: bytes | None = None,
    content_type: str | None = None,
) -> HealthSummaryRecord:
    """Answers user_input against the data-summary context already stored on OpenAI's side under
    previous_response_id (either a /data_summary call or an earlier /health_summary follow-up).
    Does not query SleepRecord/HealthRecord/DeviceRecord — this stage relies entirely on the
    chained OpenAI context for device data, per health_summary_prompt.md's framing.

    An attached image rides along in this same call (see ai_client.generate_json_response) so
    it also becomes part of that stored context for any further follow-up.
    """
    mac_address, user_input, previous_response_id = _validate(mac_address, user_input, previous_response_id)

    try:
        prompt = ai_client.with_language(_SYSTEM_PROMPT, "zh")
        result, response_id, _usage = ai_client.generate_json_response(
            prompt,
            f"userInput: {user_input}",
            previous_response_id,
            image_bytes=image_bytes,
            mime_type=content_type,
        )
    except Exception as e:  # noqa: BLE001
        logger.exception("AI health summary generation failed")
        raise AnalysisError(502, "健康摘要生成失敗", code="SUMMARY_GENERATION_FAILED") from e

    pic_id = _save_uploaded_image(db, mac_address, image_bytes, content_type) if image_bytes else None

    record = HealthSummaryRecord(
        mac_address=mac_address,
        user_input=user_input,
        data_summary_response_id=previous_response_id,
        health_summary_response_id=response_id,
        pic_id=pic_id,
        health_summary=result,
    )
    db.add(record)
    db.commit()
    db.refresh(record)
    return record
