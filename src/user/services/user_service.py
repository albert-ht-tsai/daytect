from datetime import datetime, timezone

from sqlalchemy.orm import Session

from src.core.config import BASE_URL
from src.user.models.user_model import User
from src.user.schemas.user_schema import (
    BmiData,
    BmiResponse,
    BodyInsightData,
    BodyInsightRequest,
    BodyInsightResponse,
    MeData,
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
        data=MeData(
            id=user.id,
            email=user.email,
            name=user.name,
            avatar_url=f"{BASE_URL}/avatar/user_{user.id}.png",
        )
    )


def update_me(db: Session, user: User, data: MeUpdateRequest) -> MeUpdateResponse:
    for field, value in data.model_dump(exclude_unset=True).items():
        setattr(user, field, value)
    db.add(user)
    db.commit()
    return MeUpdateResponse()


# ── /users/me/body-insight ────────────────────────────────────────────────────

def get_body_insight(user: User) -> BodyInsightResponse:
    return BodyInsightResponse(data=BodyInsightData.model_validate(user))


def upsert_body_insight(db: Session, user: User, data: BodyInsightRequest) -> BodyInsightResponse:
    for field, value in data.model_dump(exclude_unset=True).items():
        setattr(user, field, value)
    db.add(user)
    db.commit()
    db.refresh(user)
    return BodyInsightResponse(
        data=BodyInsightData.model_validate(user),
        message="Body insight saved successfully.",
    )


# ── /users/me/bmi ─────────────────────────────────────────────────────────────

def get_bmi(user: User) -> BmiResponse:
    score, category = _compute_bmi(user)
    return BmiResponse(
        data=BmiData(
            score=score,
            bmi_category=category,
            calculated_at=datetime.now(timezone.utc) if score is not None else None,
        )
    )
