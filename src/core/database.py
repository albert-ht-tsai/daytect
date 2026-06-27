from fastapi import Depends, HTTPException, status
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
        _run_migrations()
        logger.info("Database tables ensured")
    except SQLAlchemyError as e:
        logger.exception("Database initialization failed")
        raise


def _run_migrations() -> None:
    migrations = [
        "ALTER TABLE health_records ADD COLUMN IF NOT EXISTS skin_temperature JSON",
        "ALTER TABLE health_records ADD COLUMN IF NOT EXISTS respiratory_rate JSON",
        "ALTER TABLE health_records ADD COLUMN IF NOT EXISTS apnea JSON",
        "ALTER TABLE health_records ADD COLUMN IF NOT EXISTS cardiac_load JSON",
        "ALTER TABLE health_records ADD COLUMN IF NOT EXISTS sport_status JSON",
        "ALTER TABLE health_records ADD COLUMN IF NOT EXISTS blood_glucose JSON",
        "ALTER TABLE health_records ADD COLUMN IF NOT EXISTS blood_component JSON",
        # ai_health_summary_jobs: migrate device_id → user_id
        "ALTER TABLE ai_health_summary_jobs ADD COLUMN IF NOT EXISTS user_id INTEGER",
        "ALTER TABLE ai_health_summary_jobs DROP COLUMN IF EXISTS device_id",
        # backfill: remove orphaned rows that have no user_id (legacy device-based data)
        "DELETE FROM ai_health_summary_jobs WHERE user_id IS NULL",
        "ALTER TABLE ai_health_summary_jobs ALTER COLUMN user_id SET NOT NULL",
        # health_records: migrate device_id → user_id, add source_mac_address
        "ALTER TABLE health_records ADD COLUMN IF NOT EXISTS user_id INTEGER",
        "ALTER TABLE health_records ADD COLUMN IF NOT EXISTS source_mac_address VARCHAR(17)",
        "ALTER TABLE health_records DROP COLUMN IF EXISTS device_id",
        "ALTER TABLE health_records DROP CONSTRAINT IF EXISTS uq_health_records_device_date",
        # backfill: remove orphaned rows that have no user_id (legacy device-based data)
        "DELETE FROM health_records WHERE user_id IS NULL",
        "ALTER TABLE health_records ALTER COLUMN user_id SET NOT NULL",
        "CREATE UNIQUE INDEX IF NOT EXISTS uq_health_records_user_date ON health_records (user_id, date)",
    ]
    with engine.begin() as conn:
        for stmt in migrations:
            conn.execute(text(stmt))