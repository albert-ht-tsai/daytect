from contextlib import asynccontextmanager

from dotenv import load_dotenv
from fastapi import APIRouter, FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from src.assistant.api import router as assistant_router
from src.assistant.models.question_summary_model import QuestionSummaryRecord  # noqa: F401
from src.auth.api import router as auth_router
from src.auth.models.revoked_token_model import RevokedTokenRecord  # noqa: F401
from src.auth.models.user_model import UserRecord  # noqa: F401
from src.auth.models.verification_code_model import VerificationCodeRecord  # noqa: F401
from src.core.database import init_db
from src.core.deps import AuthenticationError
from src.device.api import router as device_router
from src.device.models.activity_model import ActivityRecord  # noqa: F401
from src.device.models.device_model import DeviceRecord  # noqa: F401
from src.device.models.health_model import HealthRecord  # noqa: F401
from src.device.models.sleep_model import SleepRecord  # noqa: F401
from src.feedback.api import router as feedback_router
from src.feedback.models.feedback_model import FeedbackRecord  # noqa: F401
from src.health_report.api import router as health_report_router
from src.health_report.models.health_report_model import HealthReportRecord  # noqa: F401

load_dotenv()


@asynccontextmanager
async def lifespan(app: FastAPI):
    init_db()
    yield


app = FastAPI(lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.exception_handler(AuthenticationError)
async def authentication_error_handler(request: Request, exc: AuthenticationError) -> JSONResponse:
    return JSONResponse(
        status_code=401,
        content={"success": False, "error": {"code": exc.code, "message": exc.message}},
    )

v1_router = APIRouter(prefix="/v1")
v1_router.include_router(device_router)
v1_router.include_router(assistant_router)
v1_router.include_router(auth_router)
v1_router.include_router(feedback_router)
v1_router.include_router(health_report_router)

app.include_router(v1_router)
