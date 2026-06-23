import os
from contextlib import asynccontextmanager

from dotenv import load_dotenv
from fastapi import APIRouter, FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles

from src.about.api import router as about_router
from src.auth.api import router as auth_router
from src.core.config import AVATAR_DIR
from src.core.database import init_db
from src.feedback.api import router as feedback_router
from src.health.api import router as health_router
from src.profile.api import router as user_router
from src.device.api import router as user_device_router
from src.report.api import router as report_router

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

os.makedirs(AVATAR_DIR, exist_ok=True)
app.mount("/avatar", StaticFiles(directory=AVATAR_DIR), name="avatar")

v1_router = APIRouter(prefix="/v1")
v1_router.include_router(auth_router)
v1_router.include_router(user_router)
v1_router.include_router(user_device_router)
v1_router.include_router(health_router)
v1_router.include_router(feedback_router)
v1_router.include_router(about_router)
v1_router.include_router(report_router)

app.include_router(v1_router)
