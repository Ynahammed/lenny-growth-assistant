"""Database connection and session factory.

PostgreSQL is the default (assignment requirement); a postgres:// or
postgresql:// URL — the style Supabase and Railway hand out — is normalized
to the psycopg driver. SQLite still works for throwaway local runs by
setting DATABASE_URL explicitly.
"""
import logging
from typing import Generator
from sqlalchemy import create_engine, event
from sqlalchemy.engine import Engine
from sqlalchemy.orm import sessionmaker, Session
from app.config import settings
from app.database.models import Base

logger = logging.getLogger("lenny_growth.database")


def _normalize_database_url(url: str) -> str:
    """Rewrite bare postgres URLs to the psycopg driver dialect."""
    if url.startswith("postgres://"):
        # Heroku/Supabase legacy scheme; psycopg2/psycopg treat it as postgresql://
        url = "postgresql://" + url[len("postgres://"):]
    if url.startswith("postgresql://"):
        url = url.replace("postgresql://", "postgresql+psycopg://", 1)
    return url


def _connect_args_and_engine_kwargs(url: str) -> dict:
    if url.startswith("sqlite"):
        # check_same_thread: FastAPI's threadpool shares the engine across
        # threads. FK enforcement is wired below via a connect-time pragma
        # (SQLite skips it unless asked, which historically allowed deletes
        # to orphan messages/artifacts).
        return {"connect_args": {"check_same_thread": False}}
    # Postgres: discard stale pooled connections (Supabase pooler restarts,
    # Railway deploys) and cap pool size for free-tier connection limits.
    return {
        "pool_pre_ping": True,
        "pool_size": 5,
        "max_overflow": 5,
        "pool_recycle": 1800,
    }


DATABASE_URL = _normalize_database_url(settings.DATABASE_URL)
engine = create_engine(DATABASE_URL, **_connect_args_and_engine_kwargs(DATABASE_URL))


@event.listens_for(Engine, "connect")
def _set_sqlite_pragma(dbapi_connection, _connection_record):
    """Enforce foreign keys on every new SQLite connection."""
    if DATABASE_URL.startswith("sqlite"):
        cursor = dbapi_connection.cursor()
        cursor.execute("PRAGMA foreign_keys=ON")
        cursor.close()

SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

def init_db():
    """Initializes the database schema.

    Raises with an actionable message when Postgres is unreachable — startup
    failure should say exactly what to run, not surface a raw driver error.
    """
    try:
        Base.metadata.create_all(bind=engine)
        logger.info("Database tables initialized successfully (%s).", engine.url.render_as_string(hide_password=True))
    except Exception as e:
        logger.error("Failed to initialize database tables: %s", e, exc_info=True)
        raise RuntimeError(
            "Cannot reach PostgreSQL at the URL in DATABASE_URL. "
            "Start the bundled one with 'docker compose up -d db', or point "
            "DATABASE_URL at a Supabase/Railway instance, or set "
            "DATABASE_URL=sqlite:///lenny_growth.db for a SQLite fallback."
        ) from e

def get_db() -> Generator[Session, None, None]:
    """Dependency for obtaining a SQLAlchemy session."""
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
