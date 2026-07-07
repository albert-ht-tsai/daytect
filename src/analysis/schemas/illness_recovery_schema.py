from typing import Literal

from pydantic import BaseModel

IllnessLevel = Literal["low", "medium", "high", "unknown"]
RecoveryStatus = Literal["recovered", "partially_recovered", "not_recovered", "unknown"]
Trend = Literal["improving", "stable", "worsening", "unknown"]
JointStatus = Literal["NORMAL", "UNDER_RECOVERED", "POSSIBLE_ILLNESS", "POSSIBLE_ILLNESS_RECOVERING", "UNKNOWN"]


class IllnessRecoveryRequest(BaseModel):
    macAddress: str
    date: str
    language: Literal["en", "zh"] = "en"


class IllnessRecoveryResponse(BaseModel):
    id: int
    macAddress: str
    date: str
    illness_level: IllnessLevel
    recovery_status: RecoveryStatus
    trend: Trend
    joint_status: JointStatus
    main_findings: list[str]
    alternative_explanation: str | None = None
    summary: str
