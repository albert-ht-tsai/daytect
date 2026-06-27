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
        _run_migrations()
        Base.metadata.create_all(bind=engine)
        logger.info("Database tables ensured")
    except SQLAlchemyError as e:
        logger.exception("Database initialization failed")
        raise


def _run_migrations() -> None:
    stmts = [
        # Rename ai_health_summary_chunks → health_summary_chunks (safe: only if old exists and new doesn't)
        """DO $$ BEGIN
  IF EXISTS (SELECT 1 FROM information_schema.tables WHERE table_schema='public' AND table_name='ai_health_summary_chunks')
     AND NOT EXISTS (SELECT 1 FROM information_schema.tables WHERE table_schema='public' AND table_name='health_summary_chunks')
  THEN ALTER TABLE ai_health_summary_chunks RENAME TO health_summary_chunks; END IF;
END $$""",
        # Rename ai_health_summary_jobs → health_summary_jobs (safe: only if old exists and new doesn't)
        """DO $$ BEGIN
  IF EXISTS (SELECT 1 FROM information_schema.tables WHERE table_schema='public' AND table_name='ai_health_summary_jobs')
     AND NOT EXISTS (SELECT 1 FROM information_schema.tables WHERE table_schema='public' AND table_name='health_summary_jobs')
  THEN ALTER TABLE ai_health_summary_jobs RENAME TO health_summary_jobs; END IF;
END $$""",
        # Drop removed raw data tables
        "DROP TABLE IF EXISTS raw_health_records CASCADE",
        "DROP TABLE IF EXISTS raw_activity CASCADE",
        "DROP TABLE IF EXISTS raw_sleep_data CASCADE",
        # Drop old health_records only if it still has the legacy schema (no 'datetime' column)
        """DO $$ BEGIN
  IF EXISTS (SELECT 1 FROM information_schema.tables WHERE table_schema='public' AND table_name='health_records')
     AND NOT EXISTS (SELECT 1 FROM information_schema.columns WHERE table_schema='public' AND table_name='health_records' AND column_name='datetime')
  THEN DROP TABLE health_records CASCADE; END IF;
END $$""",
    ]
    with engine.begin() as conn:
        for stmt in stmts:
            conn.execute(text(stmt))
