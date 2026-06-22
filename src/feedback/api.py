from fastapi import APIRouter

from src.core.deps import CurrentUser, SessionDep
from src.feedback.schemas.feedback_schema import SubmitFeedbackData, SubmitFeedbackRequest
from src.feedback.services.feedback_service import submit_feedback

router = APIRouter(prefix="/feedback", tags=["feedback"])


@router.post("", status_code=201)
def submit_feedback_endpoint(body: SubmitFeedbackRequest, db: SessionDep, current_user: CurrentUser):
    feedback = submit_feedback(db, current_user, body)
    return {
        "success": True,
        "data": SubmitFeedbackData(ticket_id=f"ticket_{feedback.id}"),
        "message": "Feedback submitted successfully.",
    }
