from fastapi import APIRouter, File, Form, UploadFile
from fastapi.responses import JSONResponse

from src.analysis.schemas.analysis_schema import (
    AnalysisResponse,
    CompactSummaryRequest,
    CompactSummaryResponse,
    PromptPreviewRequest,
    PromptPreviewResponse,
)
from src.analysis.services import analysis_service, summary_compaction_service
from src.analysis.services.errors import AnalysisError
from src.core.deps import SessionDep

router = APIRouter(prefix="/analysis", tags=["analysis"])


def _error_response(error: AnalysisError) -> JSONResponse:
    return JSONResponse(
        status_code=error.status_code,
        content={"success": False, "message": error.message, "data": None},
    )


async def _read_single_image(image: list[UploadFile]) -> tuple[bytes | None, str | None]:
    if len(image) > 1:
        raise AnalysisError(400, "一次最多上傳 1 張圖片")
    picked = image[0] if image else None
    if picked is None:
        return None, None
    return await picked.read(), picked.content_type


@router.post("/request", response_model=AnalysisResponse)
async def request_endpoint(
    db: SessionDep,
    macAddress: str = Form(...),
    session_id: str | None = Form(None),
    prev_summary: str | None = Form(None),
    message: str | None = Form(None),
    image: list[UploadFile] = File(default_factory=list),
    language: str = Form("en"),
):
    try:
        image_bytes, content_type = await _read_single_image(image)
        summary, session_id = analysis_service.handle_request(
            db,
            macAddress,
            session_id,
            message,
            prev_summary,
            image_bytes,
            content_type,
            language,
        )
    except AnalysisError as e:
        return _error_response(e)
    return {
        "success": True,
        "healthSummary": summary["healthSummary"],
        "fatigueSummary": summary["fatigueSummary"],
        "recoverySummary": summary["recoverySummary"],
        "session_id": session_id,
    }


@router.post("/request/preview", response_model=PromptPreviewResponse)
def request_preview_endpoint(body: PromptPreviewRequest, db: SessionDep):
    """Debug-only: returns the exact system prompt + user payload /request would send to the
    AI, without calling OpenAI and without persisting anything. No image support (identifying
    one requires an OpenAI vision call)."""
    try:
        preview = analysis_service.build_prompt_preview(
            db, body.macAddress, body.session_id, body.message, body.prev_summary, body.language
        )
    except AnalysisError as e:
        return _error_response(e)
    return {"success": True, **preview}


@router.post("/compact-summary", response_model=CompactSummaryResponse)
def compact_summary_endpoint(body: CompactSummaryRequest, db: SessionDep):
    try:
        summary, source_count = summary_compaction_service.compact_summary(
            db, body.macAddress, body.session_id, body.language
        )
    except AnalysisError as e:
        return _error_response(e)
    return {
        "success": True,
        "message": summary,
        "session_id": body.session_id,
        "source_count": source_count,
    }


@router.get("/compact-summary", response_model=CompactSummaryResponse)
def get_compact_summary_endpoint(macAddress: str, session_id: str, db: SessionDep):
    result = summary_compaction_service.get_compact_summary(db, macAddress, session_id)
    if result is None:
        return _error_response(AnalysisError(404, "找不到對應的對話重點摘要"))
    summary, source_count = result
    return {
        "success": True,
        "message": summary,
        "session_id": session_id,
        "source_count": source_count,
    }
