from sqlalchemy import create_engine, text
from sqlalchemy.orm import sessionmaker, declarative_base
from sqlalchemy.exc import SQLAlchemyError
from src.core.logging import logger
from dotenv import load_dotenv
import os

load_dotenv()

AWS_RDS_URL = os.getenv("AWS_RDS_URL")

engine = create_engine(AWS_RDS_URL)

SessionLocal = sessionmaker(
    autocommit=False,
    autoflush=False,
    bind=engine
)

Base = declarative_base()


def init_db() -> None:
    try:
        with engine.connect() as conn:
            conn.execute(text("SELECT 1"))
        logger.info("Database connection successful")
        Base.metadata.create_all(bind=engine)
        logger.info("Database tables ensured")
        _run_migrations()
        Base.metadata.create_all(bind=engine)
    except SQLAlchemyError as e:
        logger.exception("Database initialization failed")
        raise


def _run_migrations() -> None:
    stmts: list[str] = [
        "ALTER TABLE device_records DROP COLUMN IF EXISTS user_id",
        "ALTER TABLE device_records DROP COLUMN IF EXISTS device_id",
        "ALTER TABLE device_records DROP COLUMN IF EXISTS rssi",
        "ALTER TABLE device_records ADD COLUMN IF NOT EXISTS battery INTEGER",
        "ALTER TABLE device_records ADD COLUMN IF NOT EXISTS last_sync VARCHAR(19)",
        "ALTER TABLE device_records ADD COLUMN IF NOT EXISTS is_connected BOOLEAN NOT NULL DEFAULT FALSE",
        "DROP TABLE IF EXISTS activity_records CASCADE",
        "DROP TABLE IF EXISTS health_records CASCADE",
        "ALTER TABLE sleep_records DROP COLUMN IF EXISTS sleep_quality",
        "ALTER TABLE sleep_records DROP COLUMN IF EXISTS wake_count",
        "ALTER TABLE sleep_records DROP COLUMN IF EXISTS deep_sleep_time",
        "ALTER TABLE sleep_records DROP COLUMN IF EXISTS low_sleep_time",
        "ALTER TABLE sleep_records DROP COLUMN IF EXISTS all_sleep_time",
        "ALTER TABLE sleep_records DROP COLUMN IF EXISTS sleep_line",
        "ALTER TABLE sleep_records DROP COLUMN IF EXISTS sleep_down_hour",
        "ALTER TABLE sleep_records DROP COLUMN IF EXISTS sleep_down_minute",
        "ALTER TABLE sleep_records DROP COLUMN IF EXISTS sleep_up_hour",
        "ALTER TABLE sleep_records DROP COLUMN IF EXISTS sleep_up_minute",
        "ALTER TABLE sleep_records ADD COLUMN IF NOT EXISTS sleep_records JSON",
        "ALTER TABLE sleep_records ADD COLUMN IF NOT EXISTS sleep_summary JSON",
        "ALTER TABLE analysis_records ADD COLUMN IF NOT EXISTS session_id VARCHAR(64)",
        "ALTER TABLE analysis_records ADD COLUMN IF NOT EXISTS openai_response_id VARCHAR(128)",
        "ALTER TABLE data_summary_records ADD COLUMN IF NOT EXISTS response_id VARCHAR(128)",
        "ALTER TABLE data_summary_records ADD COLUMN IF NOT EXISTS pic_id VARCHAR(64)",
        "ALTER TABLE health_summary_records ADD COLUMN IF NOT EXISTS pic_id VARCHAR(64)",
        "ALTER TABLE analysis_pic_records ADD COLUMN IF NOT EXISTS session_id VARCHAR(64)",
        "ALTER TABLE health_insight_records ADD COLUMN IF NOT EXISTS sleep_quality FLOAT",
        "ALTER TABLE health_insight_records ADD COLUMN IF NOT EXISTS sleep_quality_label VARCHAR(10)",
        "ALTER TABLE health_insight_records ADD COLUMN IF NOT EXISTS sleep_quality_threshold VARCHAR(50)",
        "ALTER TABLE health_insight_records ADD COLUMN IF NOT EXISTS sleep_duration FLOAT",
        "ALTER TABLE health_insight_records ADD COLUMN IF NOT EXISTS sleep_duration_label VARCHAR(10)",
        "ALTER TABLE health_insight_records ADD COLUMN IF NOT EXISTS sleep_duration_threshold VARCHAR(50)",
        "ALTER TABLE health_insight_records ADD COLUMN IF NOT EXISTS activity_steps FLOAT",
        "ALTER TABLE health_insight_records ADD COLUMN IF NOT EXISTS activity_steps_label VARCHAR(10)",
        "ALTER TABLE health_insight_records ADD COLUMN IF NOT EXISTS activity_steps_threshold VARCHAR(50)",
        "ALTER TABLE health_insight_records ADD COLUMN IF NOT EXISTS sleep_summary TEXT",
        "ALTER TABLE health_insight_records ADD COLUMN IF NOT EXISTS activity_summary TEXT",
        "ALTER TABLE health_insight_records ADD COLUMN IF NOT EXISTS health_summary TEXT",
        "ALTER TABLE person_info_records ADD COLUMN IF NOT EXISTS mac_address VARCHAR(50)",
        # Backfills mac_address for rows saved before this column existed, from the
        # device_records row each already links to via device_id.
        """
        UPDATE person_info_records
        SET mac_address = device_records.mac_address
        FROM device_records
        WHERE person_info_records.device_id = device_records.id
          AND person_info_records.mac_address IS NULL
        """,
    ]
    with engine.begin() as conn:
        for stmt in stmts:
            conn.execute(text(stmt))
