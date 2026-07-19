from typing import Literal

from fastapi import APIRouter, File, Form, UploadFile
from fastapi.responses import JSONResponse

from src.assistant.schemas.question_summary_schema import QuestionSummaryResponse
from src.assistant.services import question_summary_service
from src.assistant.services.errors import AssistantError
from src.core.deps import SessionDep

router = APIRouter(prefix="/assistant", tags=["assistant"])


def _error_response(error: AssistantError) -> JSONResponse:
    return JSONResponse(
        status_code=error.status_code,
        content={"success": False, "error": {"code": error.code, "message": error.message}},
    )


async def _read_single_image(image: list[UploadFile | str]) -> tuple[bytes | None, str | None]:
    """Some clients submit an empty string for an untouched file input instead of omitting the
    field entirely, which FastAPI can't coerce into UploadFile — filter those out rather than
    letting them fail validation, so an optional image truly stays optional."""
    picked_files = [img for img in image if isinstance(img, UploadFile)]
    if len(picked_files) > 1:
        raise AssistantError(400, "一次最多上傳 1 張圖片", code="INVALID_PARAMETER")
    picked = picked_files[0] if picked_files else None
    if picked is None:
        return None, None
    return await picked.read(), picked.content_type


@router.post("/question", response_model=QuestionSummaryResponse)
async def question_endpoint(
    db: SessionDep,
    macAddress: str | None = Form(None),
    response_id: str | None = Form(None),
    message: str | None = Form(None),
    image: list[UploadFile | str] = File(default_factory=list),
    language: Literal["en", "zh"] = Form("zh"),
):
    """分析用戶問題並生成摘要.

    - macAddress given, no response_id: first turn of a new device-bound conversation — this
      device's own trailing-7-day sleep/health tables are queried fresh to seed context.
    - macAddress given, with response_id: chains from an earlier /assistant/question turn in the
      same device-bound conversation, without re-querying the database.
    - No macAddress: the user has no device bound; answered as a standard, non-personalized
      health assistant instead, optionally chained via response_id to an earlier turn of this
      same no-device conversation.
    """
    try:
        image_bytes, content_type = await _read_single_image(image)
        record = question_summary_service.generate_question_summary(
            db, macAddress, response_id, message, image_bytes, content_type, language
        )
    except AssistantError as e:
        return _error_response(e)
    ai_response = record.ai_response or {}
    return {
        "success": True,
        "data": {
            "macAddress": record.mac_address,
            "deviceBound": record.mac_address is not None,
            "category": record.category,
            "intent": record.intent,
            "confidence": record.confidence if record.confidence is not None else 0.0,
            "response": ai_response.get("response"),
            "benefits": ai_response.get("benefits", []),
            "responseId": record.response_id,
        },
    }
