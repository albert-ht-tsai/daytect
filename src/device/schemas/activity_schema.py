from typing import Any

from pydantic import BaseModel


class ActivityEntry(BaseModel):
    datetime: str
    sportValue: int | None = None
    sportStatus: list[Any] = []
    steps: int | None = None
    calories: int | None = None
    distance: float | None = None


class ActivityUploadRequest(BaseModel):
    date: str
    data: list[ActivityEntry]


class ActivityResponse(BaseModel):
    date: str
    data: list[ActivityEntry]
