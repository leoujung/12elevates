"""HTTP tests for the internal suppression routes (service-to-service, shared key)."""
import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, text
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

KEY = "test-internal-key-0123456789abcdef"


@pytest.fixture
def app_and_factory(monkeypatch):
    monkeypatch.setenv("INTERNAL_SUPPRESSION_KEY", KEY)
    from app.api.v1 import routes
    eng = create_engine("sqlite:///:memory:", connect_args={"check_same_thread": False}, poolclass=StaticPool)
    with eng.begin() as c:
        c.execute(text("create table suppression_list (id text primary key, identifier text unique not null, "
                       "kind text not null, source text not null, created_at text not null)"))
    factory = sessionmaker(bind=eng)
    app = routes.create_app(factory)
    return app, factory


def test_rejects_missing_or_wrong_key(app_and_factory):
    app, _ = app_and_factory
    c = TestClient(app)
    assert c.post("/v1/internal/suppression", json={"identifier": "081200000001"}).status_code == 401
    assert c.post("/v1/internal/suppression", json={"identifier": "081200000001"},
                  headers={"X-Internal-Key": "wrong"}).status_code == 401


def test_fails_closed_when_key_not_configured(monkeypatch, app_and_factory):
    app, _ = app_and_factory
    monkeypatch.delenv("INTERNAL_SUPPRESSION_KEY", raising=False)
    c = TestClient(app)
    r = c.post("/v1/internal/suppression", json={"identifier": "081200000001"},
               headers={"X-Internal-Key": KEY})
    assert r.status_code == 503


def test_optout_then_check_is_suppressed(app_and_factory):
    app, _ = app_and_factory
    c = TestClient(app)
    h = {"X-Internal-Key": KEY}
    assert c.post("/v1/internal/suppression", json={"identifier": "0812-0000-0001", "source": "optout"},
                  headers=h).status_code == 201
    r = c.post("/v1/internal/suppression/check", json={"identifier": "081200000001"}, headers=h)
    assert r.status_code == 200 and r.json() == {"suppressed": True}


def test_suppression_persists_across_new_app_instance(app_and_factory, monkeypatch):
    # The original bug: opt-out was lost on another instance. A fresh app on the same store must still block.
    app, factory = app_and_factory
    TestClient(app).post("/v1/internal/suppression", json={"identifier": "optout@example.test"},
                         headers={"X-Internal-Key": KEY})
    from app.api.v1 import routes
    app2 = routes.create_app(factory)
    r = TestClient(app2).post("/v1/internal/suppression/check", json={"identifier": "OPTOUT@example.test"},
                              headers={"X-Internal-Key": KEY})
    assert r.json() == {"suppressed": True}


def test_invalid_identifier_is_rejected_not_written(app_and_factory):
    app, factory = app_and_factory
    c = TestClient(app)
    r = c.post("/v1/internal/suppression", json={"identifier": "bad@"}, headers={"X-Internal-Key": KEY})
    assert r.status_code == 422
    db = factory()
    assert db.execute(text("select count(*) from suppression_list")).scalar() == 0


def test_unsuppressed_contact_passes(app_and_factory):
    app, _ = app_and_factory
    r = TestClient(app).post("/v1/internal/suppression/check", json={"identifier": "081299999999"},
                             headers={"X-Internal-Key": KEY})
    assert r.json() == {"suppressed": False}
