"""Business intake lock: endpoint must be closed by default.

With BUSINESS_INTAKE_ENABLED unset, POST /v1/inbound/business-interest
returns 503 INTAKE_DISABLED and must not touch the database.
"""
import importlib

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.api.v1 import business_interest as bi


def _client(get_db):
    app = FastAPI()
    bi.register_business_interest_routes(app, get_db)
    return TestClient(app)


BODY = {
    "referral_code": "REF-ANY",
    "name": "Test",
    "email": "t@example.com",
    "whatsapp": None,
    "notice_version": "1.0",
    "consent_business_interest": True,
    "consent_business_matching": True,
    "consent_business_followup": False,
    "event_id": "evt-lock-1",
}


class _ExplodingDB:
    """Fails the test if the route ever tries to read or write."""

    def execute(self, *a, **k):
        raise AssertionError("DB touched while intake is disabled")


def _get_db_explode():
    yield _ExplodingDB()


def test_closed_by_default(monkeypatch):
    monkeypatch.delenv("BUSINESS_INTAKE_ENABLED", raising=False)
    r = _client(_get_db_explode).post("/v1/inbound/business-interest", json=BODY)
    assert r.status_code == 503
    assert r.json()["detail"]["status"] == "INTAKE_DISABLED"


@pytest.mark.parametrize("val", ["0", "false", "no", ""])
def test_falsey_values_stay_closed(monkeypatch, val):
    monkeypatch.setenv("BUSINESS_INTAKE_ENABLED", val)
    r = _client(_get_db_explode).post("/v1/inbound/business-interest", json=BODY)
    assert r.status_code == 503


def test_enabled_flag_reaches_referral_check(monkeypatch):
    # With the flag on, the route proceeds to referral validation (422 for an
    # unknown referral), proving the gate is the only thing that closed it.
    monkeypatch.setenv("BUSINESS_INTAKE_ENABLED", "true")

    class _NoReferral:
        class _R:
            def first(self):
                return None

        def execute(self, *a, **k):
            return self._R()

    def _get_db():
        yield _NoReferral()

    r = _client(_get_db).post("/v1/inbound/business-interest", json=BODY)
    assert r.status_code == 422
    assert r.json()["detail"]["status"] == "INVALID_REFERRAL"
