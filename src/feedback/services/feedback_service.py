from datetime import datetime, timezone

from src.core.email import FEEDBACK_TO_ADDRESS, send_email
from src.feedback.schemas.feedback_schema import FeedbackRequest

EMAIL_SUBJECT = "[Daytect] New User Feedback"

EMAIL_TEMPLATE = """You have received a new feedback submission.

Submitted at: {submitted_at}

Content:
{content}
"""


def send_feedback(body: FeedbackRequest) -> None:
    email_body = EMAIL_TEMPLATE.format(
        submitted_at=datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC"),
        content=body.content,
    )
    send_email(to=FEEDBACK_TO_ADDRESS, subject=EMAIL_SUBJECT, body=email_body)
