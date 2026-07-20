import smtplib

from fastapi import APIRouter
from fastapi.responses import JSONResponse

from src.core.deps import SessionDep
from src.feedback.schemas.feedback_schema import FeedbackRequest
from src.feedback.services import feedback_service

router = APIRouter(prefix="/feedback", tags=["feedback"])


@router.post("")
def submit_feedback_endpoint(body: FeedbackRequest, db: SessionDep):
    try:
        feedback_service.send_feedback(db, body)
    except smtplib.SMTPException:
        return JSONResponse(
            status_code=502,
            content={"success": False, "message": "Failed to send feedback email", "data": None},
        )
    return {"success": True, "message": "Feedback submitted successfully"}
