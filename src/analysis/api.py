from fastapi import APIRouter, File, Form, UploadFile
from fastapi.responses import JSONResponse
from pydantic import ValidationError

from src.analysis.schemas.analysis_schema import (
    AnalysisResponse,
    CompactSummaryRequest,
    CompactSummaryResponse,
    LatestSummary,
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


def _parse_latest_summary(raw: str | None) -> LatestSummary | None:
    """latest_summary travels as a JSON-encoded string form field (multipart has no native
    nested-object type); validate it against the LatestSummary schema so a malformed
    payload fails fast with a 400 instead of silently reaching the AI prompt."""
    if raw is None or not raw.strip():
        return None
    try:
        return LatestSummary.model_validate_json(raw)
    except ValidationError as e:
        raise AnalysisError(400, f"latest_summary 格式錯誤: {e}") from e


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
    latest_summary: str | None = Form(None),
    message: str | None = Form(None),
    image: list[UploadFile] = File(default_factory=list),
    language: str = Form("en"),
):
    try:
        image_bytes, content_type = await _read_single_image(image)
        latest_summary_obj = _parse_latest_summary(latest_summary)
        answer, session_id = analysis_service.handle_request(
            db, macAddress, message, latest_summary_obj, image_bytes, content_type, language
        )
    except AnalysisError as e:
        return _error_response(e)
    return {"success": True, "message": answer, "session_id": session_id}


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
