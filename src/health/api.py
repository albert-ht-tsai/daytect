from typing import Literal

from fastapi import APIRouter
from fastapi.responses import JSONResponse

from src.core.deps import SessionDep
from src.health.schemas.health_insight_schema import BaseHealthInsightResponse
from src.health.schemas.person_info_schema import PersonInfoUploadRequest
from src.health.services import health_insight_service, person_info_service
from src.health.services.errors import HealthError

router = APIRouter(prefix="/health", tags=["health"])


def _error_response(error: HealthError) -> JSONResponse:
    return JSONResponse(
        status_code=error.status_code,
        content={"success": False, "message": error.message, "data": None},
    )


@router.post("/{macAddress}/person-info")
def upload_person_info_endpoint(macAddress: str, body: PersonInfoUploadRequest, db: SessionDep):
    device = person_info_service.upload_person_info(db, macAddress, body)
    if device is None:
        return _error_response(HealthError(404, "找不到對應設備"))
    return {"success": True, "message": "Person info saved successfully"}


@router.get("/{macAddress}/base-health-insight", response_model=BaseHealthInsightResponse)
def get_base_health_insight_endpoint(
    macAddress: str, db: SessionDep, language: Literal["en", "zh"] = "en"
):
    try:
        result = health_insight_service.generate_base_health_insight(db, macAddress, language)
    except HealthError as e:
        return _error_response(e)
    return result
