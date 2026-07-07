from typing import Literal

from fastapi import APIRouter, File, Form, UploadFile
from fastapi.responses import JSONResponse

from src.analysis.schemas.analysis_schema import (
    AnalysisRequest,
    AnalysisResponse,
    KeepRequest,
    PicIdentifyResponse,
)
from src.analysis.schemas.illness_recovery_schema import IllnessRecoveryRequest, IllnessRecoveryResponse
from src.analysis.services import analysis_service, illness_recovery_service
from src.analysis.services.errors import AnalysisError
from src.core.deps import SessionDep

router = APIRouter(prefix="/analysis", tags=["analysis"])


def _error_response(error: AnalysisError) -> JSONResponse:
    return JSONResponse(
        status_code=error.status_code,
        content={"success": False, "message": error.message, "data": None},
    )


@router.post("/request", response_model=AnalysisResponse)
def request_endpoint(body: AnalysisRequest, db: SessionDep):
    try:
        answer, session_id = analysis_service.handle_request(db, body.macAddress, body.message, body.language)
    except AnalysisError as e:
        return _error_response(e)
    return {"success": True, "message": answer, "session_id": session_id}


@router.post("/keep-request", response_model=AnalysisResponse)
def keep_request_endpoint(body: KeepRequest, db: SessionDep):
    try:
        answer, session_id = analysis_service.handle_keep_request(
            db, body.macAddress, body.session_id, body.message, body.language
        )
    except AnalysisError as e:
        return _error_response(e)
    return {"success": True, "message": answer, "session_id": session_id}


@router.post("/pic-identify", response_model=PicIdentifyResponse)
async def pic_identify_endpoint(
    db: SessionDep,
    macAddress: str | None = Form(None),
    # Declared as a list (rather than a single `UploadFile = File(...)`) and optional so
    # FastAPI still documents "image" as a real multipart field in the OpenAPI schema, while
    # we keep control of validation: a single required File() silently drops every part but
    # one when a client attaches more than one "image", and a missing/empty one falls through
    # to FastAPI's own 422 body instead of this module's {"success": false, ...} contract.
    image: list[UploadFile] = File(default_factory=list),
    message: str | None = Form(None),
    language: str = Form("en"),
    session_id: str | None = Form(None),
):
    if len(image) > 1:
        return _error_response(AnalysisError(400, "一次最多上傳 1 張圖片"))

    picked = image[0] if image else None
    image_bytes = await picked.read() if picked is not None else b""
    content_type = picked.content_type if picked is not None else None

    try:
        pic_id = analysis_service.handle_pic_identify(
            db, macAddress, image_bytes, content_type, message, language, session_id
        )
    except AnalysisError as e:
        return _error_response(e)
    return {"success": True, "message": "圖片辨識成功", "data": {"pic_id": pic_id}}


@router.get("/pic-answer", response_model=AnalysisResponse)
def pic_answer_endpoint(macAddress: str, pic_id: str, db: SessionDep, language: Literal["en", "zh"] = "en"):
    try:
        answer, session_id = analysis_service.handle_pic_answer(db, macAddress, pic_id, language)
    except AnalysisError as e:
        return _error_response(e)
    return {"success": True, "message": answer, "session_id": session_id}


@router.post("/illness-recovery", response_model=IllnessRecoveryResponse)
def create_illness_recovery_endpoint(body: IllnessRecoveryRequest, db: SessionDep):
    try:
        result = illness_recovery_service.generate_illness_recovery(
            db, body.macAddress, body.date, body.language
        )
    except AnalysisError as e:
        return _error_response(e)
    return result


@router.get("/illness-recovery", response_model=IllnessRecoveryResponse)
def get_illness_recovery_endpoint(macAddress: str, date: str, db: SessionDep):
    result = illness_recovery_service.get_illness_recovery(db, macAddress, date)
    if result is None:
        return _error_response(AnalysisError(404, "找不到對應的生病/恢復分析結果"))
    return result
