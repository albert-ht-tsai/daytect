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
    ]
    with engine.begin() as conn:
        for stmt in migrations:
            conn.execute(text(stmt))