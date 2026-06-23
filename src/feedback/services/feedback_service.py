from sqlalchemy.orm import Session

from src.feedback.models.feedback_model import Feedback
from src.feedback.schemas.feedback_schema import SubmitFeedbackRequest
from src.profile.models.user_model import User


def submit_feedback(db: Session, user: User, body: SubmitFeedbackRequest) -> Feedback:
    feedback = Feedback(user_id=user.id, type=body.type, subject=body.subject, message=body.message)
    db.add(feedback)
    db.commit()
    db.refresh(feedback)
    return feedback
