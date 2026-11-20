"""Database connection. The URL comes from the environment only (never hard-coded, never printed).

Phase 1 tests run on SQLite in memory. The Postgres test (tests/test_postgres_smoke.py)
runs only when APP_TEST_DATABASE_URL is set, so the suite stays green without Postgres.
"""
import os

from sqlalchemy import create_engine
from sqlalchemy.engine import Engine


def make_engine(url: str | None = None) -> Engine:
    url = url or os.environ.get("APP_DATABASE_URL", "")
    if not url:
        raise RuntimeError("APP_DATABASE_URL is not set")
    return create_engine(url, pool_pre_ping=True)
