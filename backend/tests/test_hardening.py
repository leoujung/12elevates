"""Phase 6 hardening: spoofed X-Forwarded-For must not evade the login limit; docs off by default."""
from app.api.v1.routes import create_app
from tests.test_api_phase1 import client, login  # noqa: F401 (pytest fixture)


def test_spoofed_forwarded_for_cannot_evade_login_limit(client):
    # Each attempt claims a different "client" in X-Forwarded-For. The proxy appends the real IP
    # last; with TestClient the peer is the test host, so the appended value is what counts.
    statuses = []
    for i in range(14):
        r = client.post("/v1/auth/login", headers={"X-Forwarded-For": f"10.0.0.{i}, 203.0.113.9"},
                        json={"email": "andi@example.test", "password": "wrong-probe"})
        statuses.append(r.status_code)
    assert statuses[-1] == 429


def test_docs_are_off_by_default(monkeypatch, client):
    monkeypatch.delenv("APP_ENABLE_DOCS", raising=False)
    app = client.app
    assert app.docs_url is None and app.openapi_url is None


def test_docs_on_when_explicitly_enabled(monkeypatch):
    monkeypatch.setenv("APP_ENABLE_DOCS", "1")
    from sqlalchemy.orm import sessionmaker
    from sqlalchemy import create_engine
    from app.models.core import Base
    eng = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(eng)
    app = create_app(sessionmaker(bind=eng))
    assert app.docs_url == "/docs" and app.openapi_url == "/openapi.json"
