from datetime import date as date_cls
from typing import Literal

from pydantic import BaseModel


class CreateReportTaskRequest(BaseModel):
    report_type: Literal["daily", "weekly"]
    date: date_cls
    language: str = "en"
