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
    except SQLAlchemyError as e:
        logger.exception("Database initialization failed")
        raise


def _run_migrations() -> None:
    stmts: list[str] = [
        "ALTER TABLE device_records DROP COLUMN IF EXISTS user_id",
        "ALTER TABLE device_records DROP COLUMN IF EXISTS device_id",
        "ALTER TABLE device_records DROP COLUMN IF EXISTS rssi",
        "ALTER TABLE device_records DROP COLUMN IF EXISTS battery",
        "ALTER TABLE device_records DROP COLUMN IF EXISTS is_connected",
        "ALTER TABLE device_records DROP COLUMN IF EXISTS last_synced_at",
    ]
    with engine.begin() as conn:
        for stmt in stmts:
            conn.execute(text(stmt))
