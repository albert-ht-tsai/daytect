from fastapi import UploadFile
from sqlalchemy.orm import Session

from src.core.files import save_avatar
from src.profile.models.user_model import User
from src.profile.schemas.user_schema import (
    AvatarData,
    AvatarUpdateResponse,
    BodyInsightBmi,
    BodyInsightData,
    BodyInsightGoals,
    BodyInsightRequest,
    BodyInsightResponse,
    MeResponse,
    MeUpdateRequest,
    MeUpdateResponse,
)

_HEIGHT_TO_M = {"cm": 0.01, "m": 1.0, "inch": 0.0254}
_WEIGHT_TO_KG = {"kg": 1.0, "lb": 0.453592}

# Thresholds: upper bound (exclusive) → label
# underweight: 0–18.4 | normal: 18.5–24.9 | overweight: 25–29.9 | obese: 30+
_BMI_THRESHOLDS = [
    (18.5,         "Underweight"),
    (25.0,         "Normal"),
    (30.0,         "Overweight"),
    (float("inf"), "Obese"),
]


def _compute_bmi(user: User) -> tuple[float | None, str | None]:
    height_m = (user.height or 0) * _HEIGHT_TO_M.get(user.height_unit or "cm", 0.01)
    weight_kg = (user.weight or 0) * _WEIGHT_TO_KG.get(user.weight_unit or "kg", 1.0)
    if height_m <= 0 or weight_kg <= 0:
        return None, None
    score = round(weight_kg / (height_m ** 2), 1)
    category = next(cat for threshold, cat in _BMI_THRESHOLDS if score < threshold)
    return score, category


# ── /users/me ─────────────────────────────────────────────────────────────────

def get_me(user: User) -> MeResponse:
    return MeResponse(
        id=user.id,
        email=user.email,
        name=user.name,
        avatar=user.avatar,
        region=user.region,
    )


def update_me(db: Session, user: User, data: MeUpdateRequest) -> MeUpdateResponse:
    for field, value in data.model_dump(exclude_unset=True).items():
        setattr(user, field, value)
    db.add(user)
    db.commit()
    return MeUpdateResponse()


def update_my_avatar(db: Session, user: User, file: UploadFile) -> AvatarUpdateResponse:
    user.avatar = save_avatar(file, "user", user.id)
    db.add(user)
    db.commit()
    return AvatarUpdateResponse(data=AvatarData(avatar_url=user.avatar))


# ── /users/me/body-insight ────────────────────────────────────────────────────

def _build_body_insight_data(user: User) -> BodyInsightData:
    score, category = _compute_bmi(user)
    return BodyInsightData(
        user_id=user.id,
        height=user.height,
        height_unit=user.height_unit,
        weight=user.weight,
        weight_unit=user.weight_unit,
        age=user.age,
        sex=user.sex,
        goals=BodyInsightGoals(
            step_aim=user.step_aim,
            step_aim_type=user.step_aim_type,
            sleep_aim=user.sleep_aim,
            sleep_aim_type=user.sleep_aim_type,
        ),
        bmi=BodyInsightBmi(value=score, level=category),
    )


def get_body_insight(user: User) -> BodyInsightResponse:
    return BodyInsightResponse(data=_build_body_insight_data(user))


def upsert_body_insight(db: Session, user: User, data: BodyInsightRequest) -> BodyInsightResponse:
    for field, value in data.model_dump(exclude_unset=True).items():
        setattr(user, field, value)
    db.add(user)
    db.commit()
    db.refresh(user)
    return BodyInsightResponse(
        data=_build_body_insight_data(user),
        message="Body insight saved successfully.",
    )
