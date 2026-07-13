import json
import os
from pathlib import Path

from sqlalchemy.orm import Session

from src.assistant.models.profile_summary_model import ProfileSummaryRecord
from src.assistant.services.errors import AssistantError
from src.core import ai_client, files
from src.core.logging import logger
from src.device.models.device_model import DeviceRecord
from src.health.models.person_info_model import PersonInfoRecord

PROFILE_SUMMARY_MAX_TOKENS = int(os.getenv("ASSISTANT_PROFILE_MAX_TOKENS", 500))

_PROMPT_RULES = (Path(__file__).parent / "profile_prompt.md").read_text(encoding="utf-8")
_SYSTEM_PROMPT = f"""{_PROMPT_RULES}

Return a single JSON object: {{"summary": "<string>"}}."""

# Age at which the elderly-tier standard applies, absent a disqualifying medical history.
_ELDERLY_AGE_MIN = 65
_NO_HISTORY_VALUES = {"", "無", "无", "none", "n/a", "na"}


def _has_medical_history(value: str | None) -> bool:
    return bool(value) and value.strip().lower() not in _NO_HISTORY_VALUES


def _determine_level(age: int, medical_history: str | None) -> tuple[str, str, str]:
    """Returns (level, level_label, standard) computed deterministically from the person's
    profile — the level classification itself is never left to the AI (only the natural-
    language write-up is), matching this codebase's system-computes-status /
    AI-writes-narrative split (see data_summary_service._compute_metric_status).

    A disqualifying medical history always takes precedence over the age-based tier, since it
    signals a need for closer (看護級) monitoring regardless of how old the user is."""
    if _has_medical_history(medical_history):
        return "attention", "特別注意", "看護級健康標準"
    if age >= _ELDERLY_AGE_MIN:
        return "low", "偏低", "老人健康標準"
    return "normal", "正常", "成人健康標準"


def _validate_mac_address(mac_address: str | None) -> str:
    if not mac_address or not mac_address.strip():
        raise AssistantError(400, "macAddress 不可為空", code="INVALID_PARAMETER")
    return mac_address.strip()


def _save_uploaded_image(image_bytes: bytes, content_type: str | None) -> str | None:
    pic_id = files.generate_pic_id()
    return files.save_analysis_image(image_bytes, content_type, pic_id)


def _build_payload(info: PersonInfoRecord, level_label: str, standard: str) -> dict:
    return {
        "sex": info.sex,
        "age": info.age,
        "height": info.height,
        "weight": info.weight,
        "allergy": info.allergy or "無",
        "medicalHistory": info.medical_history or "無",
        "level": level_label,
        "standard": standard,
    }


def generate_profile_summary(
    db: Session,
    mac_address: str | None,
    previous_response_id: str | None,
    image_bytes: bytes | None,
    content_type: str | None,
    language: str = "zh",
) -> ProfileSummaryRecord:
    """Stage 1 of the assistant flow: summarizes the user's body characteristics and computes
    their body-characteristic level, which /assistant/trend then reasons from via
    previous_response_id chaining."""
    mac_address = _validate_mac_address(mac_address)

    device = db.query(DeviceRecord).filter(DeviceRecord.mac_address == mac_address).first()
    if device is None:
        raise AssistantError(404, "找不到對應設備", code="DEVICE_NOT_FOUND")

    person_info = db.query(PersonInfoRecord).filter(PersonInfoRecord.device_id == device.id).first()
    if person_info is None:
        raise AssistantError(400, "用戶尚未保存身體特徵信息，請先上傳個人身體特徵資料", code="PERSON_INFO_NOT_FOUND")

    level, level_label, standard = _determine_level(person_info.age, person_info.medical_history)
    payload = _build_payload(person_info, level_label, standard)

    try:
        prompt = ai_client.with_language(_SYSTEM_PROMPT, language)
        result, response_id, _usage = ai_client.generate_json_response(
            prompt,
            f"Input:\n{json.dumps(payload, default=str)}",
            previous_response_id,
            image_bytes=image_bytes,
            mime_type=content_type,
            max_output_tokens=PROFILE_SUMMARY_MAX_TOKENS,
        )
    except Exception as e:  # noqa: BLE001
        logger.exception("AI profile summary generation failed")
        raise AssistantError(502, "身體特徵摘要生成失敗", code="SUMMARY_GENERATION_FAILED") from e

    image_path = _save_uploaded_image(image_bytes, content_type) if image_bytes else None

    record = db.query(ProfileSummaryRecord).filter(ProfileSummaryRecord.mac_address == mac_address).first()
    if record is None:
        record = ProfileSummaryRecord(mac_address=mac_address)
        db.add(record)

    record.sex = person_info.sex
    record.age = person_info.age
    record.height = person_info.height
    record.weight = person_info.weight
    record.allergy = person_info.allergy
    record.medical_history = person_info.medical_history
    record.level = level
    record.level_label = level_label
    record.standard = standard
    record.summary = str(result.get("summary") or "")
    record.image_path = image_path
    record.response_id = response_id
    db.commit()
    db.refresh(record)
    return record
