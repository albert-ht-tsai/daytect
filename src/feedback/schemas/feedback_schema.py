import re
from typing import Annotated

from pydantic import AfterValidator, BaseModel, Field

EMAIL_REGEX = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")


def _validate_email(value: str) -> str:
    if not EMAIL_REGEX.match(value):
        raise ValueError("Invalid email format")
    return value.lower()


EmailField = Annotated[str, AfterValidator(_validate_email)]


class FeedbackRequest(BaseModel):
    email: EmailField
    content: str = Field(min_length=1, max_length=5000)
