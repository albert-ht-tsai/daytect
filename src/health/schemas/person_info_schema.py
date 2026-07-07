from typing import Literal

from pydantic import BaseModel, Field


class PersonInfoUploadRequest(BaseModel):
    sex: Literal["male", "female"]
    age: int = Field(ge=0, le=999)
    height: float = Field(ge=0, le=999)
    weight: float = Field(ge=0, le=999)
    allergy: str = ""
    medical_history: str = ""
