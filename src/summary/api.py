from fastapi import APIRouter, HTTPException

from src.core.deps import SessionDep
from src.summary.schemas.summary_schema import DailyHealthSummaryResponse, SummaryRequest
from src.summary.services import summary_service

router = APIRouter(tags=["summary"])


@router.post("/summary", response_model=DailyHealthSummaryResponse)
def create_summary_endpoint(body: SummaryRequest, db: SessionDep):
    result = summary_service.generate_summary(db, body.macAddress, body.date, body.language)
    if result is None:
        raise HTTPException(status_code=404, detail={"code": 404, "message": "Device not found"})
    return result


@router.get("/summary", response_model=DailyHealthSummaryResponse)
def get_summary_endpoint(macAddress: str, date: str, db: SessionDep):
    result = summary_service.get_summary(db, macAddress, date)
    if result is None:
        raise HTTPException(status_code=404, detail={"code": 404, "message": "Summary not found"})
    return result
