from contextlib import asynccontextmanager

from dotenv import load_dotenv
from fastapi import APIRouter, FastAPI
from fastapi.middleware.cors import CORSMiddleware

from src.analysis.api import router as analysis_router
from src.analysis.models.analysis_model import AnalysisRecord  # noqa: F401
from src.analysis.models.analysis_pic_model import AnalysisPicRecord  # noqa: F401
from src.core.database import init_db
from src.device.api import router as device_router
from src.device.models.activity_model import ActivityRecord  # noqa: F401
from src.device.models.device_model import DeviceRecord  # noqa: F401
from src.device.models.health_model import HealthRecord  # noqa: F401
from src.device.models.sleep_model import SleepRecord  # noqa: F401
from src.summary.api import router as summary_router
from src.summary.models.summary_model import DailyHealthSummaryRecord  # noqa: F401

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
v1_router.include_router(device_router)
v1_router.include_router(summary_router)
v1_router.include_router(analysis_router)

app.include_router(v1_router)
