from fastapi import APIRouter, File, UploadFile

from src.core.deps import CurrentUser, SessionDep
from src.user.schemas.user_schema import (
    AvatarUpdateResponse,
    BmiResponse,
    BodyInsightRequest,
    BodyInsightResponse,
    MeResponse,
    MeUpdateRequest,
    MeUpdateResponse,
)
from src.user.services.user_service import (
    get_bmi,
    get_body_insight,
    get_me,
    update_me,
    update_my_avatar,
    upsert_body_insight,
)

router = APIRouter(prefix="/users", tags=["users"])


# ── /users/me ─────────────────────────────────────────────────────────────────

@router.get("/me", response_model=MeResponse)
def get_me_endpoint(current_user: CurrentUser):
    return get_me(current_user)


@router.put("/me", response_model=MeUpdateResponse)
def update_me_endpoint(body: MeUpdateRequest, db: SessionDep, current_user: CurrentUser):
    return update_me(db, current_user, body)


@router.post("/me/avatar", response_model=AvatarUpdateResponse)
def update_my_avatar_endpoint(db: SessionDep, current_user: CurrentUser, file: UploadFile = File(...)):
    return update_my_avatar(db, current_user, file)


# ── /users/me/body-insight ────────────────────────────────────────────────────

@router.get("/me/body-insight", response_model=BodyInsightResponse)
def get_body_insight_endpoint(current_user: CurrentUser):
    return get_body_insight(current_user)


@router.post("/me/body-insight", response_model=BodyInsightResponse, status_code=201)
def create_body_insight_endpoint(body: BodyInsightRequest, db: SessionDep, current_user: CurrentUser):
    return upsert_body_insight(db, current_user, body)


@router.put("/me/body-insight", response_model=BodyInsightResponse)
def update_body_insight_endpoint(body: BodyInsightRequest, db: SessionDep, current_user: CurrentUser):
    return upsert_body_insight(db, current_user, body)


# ── /users/me/bmi ─────────────────────────────────────────────────────────────

@router.get("/me/bmi", response_model=BmiResponse)
def get_bmi_endpoint(current_user: CurrentUser):
    return get_bmi(current_user)
