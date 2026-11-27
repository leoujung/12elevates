"""NBI read endpoint: only real (non-synthetic) rows, member-scoped.

Uses SQLite in-memory like test_api_phase1. Creates the NBI tables directly
(same columns as migration i2j3nbischema01) so no migration run is needed.
"""
from datetime import datetime

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, text
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.main import create_app


@pytest.fixture()
def db_session_factory():
    engine = create_engine(
        "sqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    with engine.begin() as conn:
        conn.execute(text("""
            CREATE TABLE nbi_matching_results (
                id TEXT PRIMARY KEY,
                job_id TEXT NOT NULL,
                member_id TEXT NOT NULL,
                prospect_id TEXT,
                fit_score INTEGER,
                intent_confidence INTEGER,
                data_confidence INTEGER,
                reason TEXT NOT NULL,
                rules_version TEXT NOT NULL,
                is_synthetic BOOLEAN NOT NULL DEFAULT 0,
                created_at DATETIME NOT NULL
            )
        """))
    return sessionmaker(bind=engine)


def _insert(Session, row_id, member_id, synthetic):
    with Session() as s:
        s.execute(text(
            "INSERT INTO nbi_matching_results "
            "(id, job_id, member_id, prospect_id, fit_score, intent_confidence, data_confidence, "
            " reason, rules_version, is_synthetic, created_at) "
            "VALUES (:id, 'job1', :m, NULL, 50, 50, 50, 'r', 'nbi-rules-v1', :syn, :ts)"
        ), {"id": row_id, "m": member_id, "syn": synthetic, "ts": datetime(2026, 11, 27)})
        s.commit()


def test_synthetic_rows_are_never_returned(db_session_factory):
    _insert(db_session_factory, "real1", "member-A", False)
    _insert(db_session_factory, "demo1", "member-A", True)
    # the route under test is registered by create_app; token issuing is
    # covered in test_api_phase1 — here we call the route function directly.
    from app.api.v1.nbi_read import register_nbi_read_routes
    from fastapi import FastAPI, Depends

    app = FastAPI()

    def get_db():
        s = db_session_factory()
        try:
            yield s
        finally:
            s.close()

    def current_member_id():
        return "member-A"

    register_nbi_read_routes(app, get_db, current_member_id)
    client = TestClient(app)
    res = client.get("/v1/nbi/results")
    assert res.status_code == 200
    ids = [item["id"] for item in res.json()["items"]]
    assert ids == ["real1"], ids
    assert all(not item["is_synthetic"] for item in res.json()["items"])


def test_other_member_rows_are_not_returned(db_session_factory):
    _insert(db_session_factory, "a1", "member-A", False)
    _insert(db_session_factory, "b1", "member-B", False)
    from app.api.v1.nbi_read import register_nbi_read_routes
    from fastapi import FastAPI

    app = FastAPI()

    def get_db():
        s = db_session_factory()
        try:
            yield s
        finally:
            s.close()

    register_nbi_read_routes(app, get_db, lambda: "member-B")
    res = TestClient(app).get("/v1/nbi/results")
    ids = [item["id"] for item in res.json()["items"]]
    assert ids == ["b1"], ids
