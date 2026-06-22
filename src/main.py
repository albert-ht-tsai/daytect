from contextlib import asynccontextmanager

from dotenv import load_dotenv
from fastapi import APIRouter, FastAPI
from fastapi.middleware.cors import CORSMiddleware

from src.about.api import router as about_router
from src.auth.api import router as auth_router
from src.core.database import init_db
from src.dashboard.api import router as dashboard_router
from src.feedback.api import router as feedback_router
from src.health.api import router as health_router
from src.health.analysis.api import router as analysis_router
from src.report.api import router as report_router
from src.user.api import router as user_router
from src.user_device.api import router as user_device_router

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

v1_router = APIRouter(prefix="/v1")
v1_router.include_router(auth_router)
v1_router.include_router(user_router)
v1_router.include_router(user_device_router)
v1_router.include_router(health_router)
v1_router.include_router(analysis_router)
v1_router.include_router(dashboard_router)
v1_router.include_router(report_router)
v1_router.include_router(feedback_router)
v1_router.include_router(about_router)

app.include_router(v1_router)
