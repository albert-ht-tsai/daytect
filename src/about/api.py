from fastapi import APIRouter
from pydantic import BaseModel

from src.core.deps import CurrentUser

router = APIRouter(prefix="/about", tags=["about"])


class AboutResponse(BaseModel):
    app_name: str = "Daytect"
    version: str = "1.0.0"
    description: str = (
        "Daytect is a daily AI health assistant that helps users understand their physical "
        "condition through wearable health data analysis."
    )
    website: str = "https://daytect.com"
    privacy_policy_url: str = "https://daytect.com/privacy"
    terms_url: str = "https://daytect.com/terms"


@router.get("", response_model=AboutResponse)
def get_about_endpoint(current_user: CurrentUser):
    return AboutResponse()
