"""Database layer tests: URL normalization and SQLite FK pragma."""
from sqlalchemy import text

from app.database import db


def test_normalize_bare_postgres_scheme():
    """Supabase/Railway hand out postgres:// URLs; the driver needs postgresql+psycopg://."""
    url = db._normalize_database_url("postgres://u:p@host:5432/dbname")
    assert url == "postgresql+psycopg://u:p@host:5432/dbname"


def test_normalize_postgresql_scheme_gets_psycopg_driver():
    url = db._normalize_database_url("postgresql://u:p@host:5432/dbname")
    assert url == "postgresql+psycopg://u:p@host:5432/dbname"


def test_normalize_psycopg_url_untouched():
    url = "postgresql+psycopg://lenny:lenny@localhost:5432/lenny_growth"
    assert db._normalize_database_url(url) == url


def test_normalize_sqlite_url_untouched():
    url = "sqlite:///lenny_growth.db"
    assert db._normalize_database_url(url) == url


def test_sqlite_engine_enforces_foreign_keys():
    """The FK pragma must be ON — without it SQLite orphans child rows on delete."""
    with db.engine.connect() as conn:
        # Only meaningful when the test env actually runs on SQLite.
        if db.DATABASE_URL.startswith("sqlite"):
            assert conn.execute(text("PRAGMA foreign_keys")).scalar() == 1
