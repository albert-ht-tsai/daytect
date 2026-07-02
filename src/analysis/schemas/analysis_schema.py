from typing import Literal

from pydantic import BaseModel


class AnalysisRequest(BaseModel):
    macAddress: str
    message: str
    language: Literal["en", "zh"] = "en"


class KeepRequest(BaseModel):
    macAddress: str
    previousAnswer: str
    message: str
    language: Literal["en", "zh"] = "en"


class AnalysisResponse(BaseModel):
    success: bool
    message: str


class PicIdentifyData(BaseModel):
    pic_id: str


class PicIdentifyResponse(BaseModel):
    success: bool
    message: str
    data: PicIdentifyData
