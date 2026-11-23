"""HTTP tests for POST /v1/internal/inbound (E1.2). Uses the real app factory and an in-memory SQLite DB."""
import os
import uuid

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from tests.test_central_prospect import SCHEMA

KEY = "k" * 40


@pytest.fixture()
def client(monkeypatch):
    monkeypatch.setenv("INTERNAL_SUPPRESSION_KEY", KEY)
    engine = create_engine("sqlite:///:memory:", poolclass=StaticPool, connect_args={"check_same_thread": False})
    with engine.begin() as c:
        for stmt in SCHEMA:
            c.exec_driver_sql(stmt)
    Session = sessionmaker(bind=engine)
    from app.api.v1 import routes
    app = routes.create_app(Session)
    return TestClient(app)


def body(**over):
    b = {
        "event_type": "WEBINAR_REGISTERED",
        "event_id": f"EVT-{uuid.uuid4().hex[:10]}",
        "member_id": "ptn_http_01",
        "lead": {"name": "Uji HTTP", "whatsapp": "081222220001", "email": "http1@example.test"},
        "consents": {"registration_processing": True, "marketing_optional": False},
        "notice_version": "v0-draft",
        "attribution": {"source": "join.html"},
    }
    b.update(over)
    return b


def test_no_key_is_rejected(client):
    r = client.post("/v1/internal/inbound", json=body())
    assert r.status_code == 401


def test_wrong_key_is_rejected(client):
    r = client.post("/v1/internal/inbound", json=body(), headers={"X-Internal-Key": "x" * 40})
    assert r.status_code == 401


def test_key_not_configured_fails_closed(monkeypatch, client):
    monkeypatch.delenv("INTERNAL_SUPPRESSION_KEY", raising=False)
    r = client.post("/v1/internal/inbound", json=body(), headers={"X-Internal-Key": KEY})
    assert r.status_code == 503


def test_valid_event_is_persisted(client):
    r = client.post("/v1/internal/inbound", json=body(), headers={"X-Internal-Key": KEY})
    assert r.status_code == 200
    assert r.json()["status"] == "PERSISTED"


def test_consent_rejection_is_422_with_stable_code(client):
    r = client.post("/v1/internal/inbound",
                    json=body(consents={"registration_processing": False}),
                    headers={"X-Internal-Key": KEY})
    assert r.status_code == 422
    assert r.json()["detail"]["status"] == "REJECTED_CONSENT"


def test_repeat_event_is_idempotent_over_http(client):
    b = body(event_id="EVT-HTTP-DUP")
    h = {"X-Internal-Key": KEY}
    assert client.post("/v1/internal/inbound", json=b, headers=h).json()["status"] == "PERSISTED"
    assert client.post("/v1/internal/inbound", json=b, headers=h).json()["status"] == "DUPLICATE_IGNORED"


def test_unknown_event_type_is_422(client):
    r = client.post("/v1/internal/inbound", json=body(event_type="NOPE"), headers={"X-Internal-Key": KEY})
    assert r.status_code == 422
