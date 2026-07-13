from typing import Literal

from fastapi import APIRouter, File, Form, UploadFile
from fastapi.responses import JSONResponse

from src.assistant.schemas.profile_summary_schema import ProfileSummaryResponse
from src.assistant.schemas.question_summary_schema import QuestionSummaryResponse
from src.assistant.schemas.trend_summary_schema import TrendSummaryResponse
from src.assistant.services import profile_summary_service, question_summary_service, trend_summary_service
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


@router.post("/profile", response_model=ProfileSummaryResponse)
async def profile_endpoint(
    db: SessionDep,
    macaddress: str = Form(...),
    previous_response_id: str | None = Form(None),
    image: list[UploadFile | str] = File(default_factory=list),
    language: Literal["en", "zh"] = Form("zh"),
):
    """Stage 1: 分析個人身體並生成摘要. Not chained from anything (previous_response_id is
    optional here — pass one only to continue this device's own profile thread), returns
    responseId to chain into /assistant/trend."""
    try:
        image_bytes, content_type = await _read_single_image(image)
        record = profile_summary_service.generate_profile_summary(
            db, macaddress, previous_response_id, image_bytes, content_type, language
        )
    except AssistantError as e:
        return _error_response(e)
    return {
        "success": True,
        "data": {
            "macAddress": record.mac_address,
            "profile": {
                "sex": record.sex,
                "age": record.age,
                "height": record.height,
                "weight": record.weight,
                "allergy": record.allergy or "",
                "medicalHistory": record.medical_history or "",
            },
            "level": record.level,
            "levelLabel": record.level_label,
            "standard": record.standard,
            "summary": record.summary,
            "previousResponseId": previous_response_id,
            "responseId": record.response_id,
        },
    }


@router.post("/trend", response_model=TrendSummaryResponse)
async def trend_endpoint(
    db: SessionDep,
    macaddress: str = Form(...),
    previous_response_id: str = Form(...),
    date: str | None = Form(None),
    image: list[UploadFile | str] = File(default_factory=list),
    language: Literal["en", "zh"] = Form("zh"),
):
    """Stage 2: 分析個人健康趨勢並生成摘要. Must be chained from /assistant/profile's
    responseId so the AI already has this user's body-characteristic level in context.
    `date` (YYYY-MM-DD, optional) is the last day of the trailing 7-day window to query;
    defaults to today (REPORT_TZ) when omitted."""
    try:
        image_bytes, content_type = await _read_single_image(image)
        record = trend_summary_service.generate_trend_summary(
            db, macaddress, previous_response_id, image_bytes, content_type, language, date
        )
    except AssistantError as e:
        return _error_response(e)
    ai_response = record.ai_response or {}
    return {
        "success": True,
        "data": {
            "macAddress": record.mac_address,
            "startDate": record.start_date,
            "endDate": record.end_date,
            "levelConsistent": record.level_consistent,
            "reassessedLevel": ai_response.get("reassessedLevel"),
            "reassessedStandard": ai_response.get("reassessedStandard"),
            "trendData": record.trend_data or {},
            "sleep": ai_response.get("sleep", {}),
            "health": ai_response.get("health", {}),
            "activity": ai_response.get("activity", {}),
            "previousResponseId": record.previous_response_id,
            "responseId": record.response_id,
        },
    }


@router.post("/question", response_model=QuestionSummaryResponse)
async def question_endpoint(
    db: SessionDep,
    macaddress: str = Form(...),
    previous_response_id: str = Form(...),
    message: str | None = Form(None),
    image: list[UploadFile | str] = File(default_factory=list),
    language: Literal["en", "zh"] = Form("zh"),
):
    """Stage 3: 分析用戶問題並生成摘要. Must be chained from /assistant/trend's responseId (or
    an earlier /assistant/question turn's responseId for a follow-up question)."""
    try:
        image_bytes, content_type = await _read_single_image(image)
        record = question_summary_service.generate_question_summary(
            db, macaddress, previous_response_id, message, image_bytes, content_type, language
        )
    except AssistantError as e:
        return _error_response(e)
    ai_response = record.ai_response or {}
    return {
        "success": True,
        "data": {
            "macAddress": record.mac_address,
            "category": record.category,
            "confidence": record.confidence if record.confidence is not None else 0.0,
            "response": ai_response.get("response"),
            "benefits": ai_response.get("benefits", []),
            "previousResponseId": record.previous_response_id,
            "responseId": record.response_id,
        },
    }
