from typing import Optional

from pydantic import BaseModel


class SubmitFeedbackRequest(BaseModel):
    user_id: Optional[str] = None
    type: str
    subject: str
    message: str


class SubmitFeedbackData(BaseModel):
    ticket_id: str
