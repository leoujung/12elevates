import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.pool import StaticPool
from sqlalchemy.orm import sessionmaker
from sqlalchemy import text
from app.models.core import Base, Member, Organization
from app.services import central_prospect as cp
from app.api.v1.business_interest import register_business_interest_routes


def _ev(consents):
    return {"event_type": "BUSINESS_INTEREST", "event_id": "c-1", "member_id": "m-biz",
            "lead": {"email": "tester@example.com", "name": "Tester"},
            "consents": consents, "notice_version": "v1.0", "attribution": {"source": "form"}}


def test_matching_consent_required_for_business():
    with pytest.raises(cp.InboundError) as e:
        cp.validate_event(_ev({"business_interest_processing": True}))
    assert e.value.code == "REJECTED_CONSENT"
    assert "business_matching" in str(e.value)


def test_business_accepted_with_matching_and_no_followup():
    out = cp.validate_event(_ev({"business_interest_processing": True, "business_matching": True}))
    assert out["event_type"] == "BUSINESS_INTEREST"


def test_followup_is_optional():
    cp.validate_event(_ev({"business_interest_processing": True, "business_matching": True,
                           "business_followup": False}))


def test_followup_not_mapped_to_marketing():
    # business_followup must not be accepted as marketing_optional substitute
    with pytest.raises(cp.InboundError):
        cp.validate_event(_ev({"business_interest_processing": True, "business_matching": True,
                               "marketing_optional": True, "business_followup": "yes"}))


def test_unknown_purpose_still_rejected():
    with pytest.raises(cp.InboundError):
        cp.validate_event(_ev({"business_interest_processing": True, "business_matching": True,
                               "made_up": True}))


_ANDI_CODE = [None]

@pytest.fixture()
def client(monkeypatch):
    monkeypatch.setenv("BUSINESS_INTAKE_ENABLED", "true")
    engine = create_engine("sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool)
    Base.metadata.create_all(engine)
    with engine.begin() as c:
        for ddl in [
            "create table if not exists suppression_list (identifier text primary key)",
            "create table if not exists cp_prospects (prospect_id text primary key, member_id text, prospect_type text, display_name text, status text, created_at text, updated_at text)",
            "create table if not exists cp_prospect_identifiers (id text primary key, prospect_id text, member_id text, kind text, value_normalized text, created_at text)",
            "create table if not exists cp_inbound_events (event_id text, event_type text, member_id text, prospect_id text, status text, payload_minimal text, received_at text)",
            "create table if not exists cp_consent_ledger (prospect_id text, member_id text, purpose text, granted boolean, notice_version text, source text, event_id text, recorded_at text)",
            "create table if not exists cp_provenance (prospect_id text, member_id text, source_page text, campaign text, referral_code text, first_event_id text, first_seen_at text)",
            "create table if not exists cp_sync_queue (prospect_id text, member_id text, event_id text, destination text, idempotency_key text, status text, attempts int, next_attempt_at text, created_at text, updated_at text)",
            "create table if not exists cp_audit_log (member_id text, actor text, action text, target_id text, reason text, at text)",
        ]:
            c.execute(text(ddl))
    S = sessionmaker(bind=engine)
    s = S()
    org = Organization(name="t")
    s.add(org)
    s.flush()
    s.add(Member(id="member-andi", organization_id=org.id, email="andi@example.test",
                 display_name="Andi", sponsor_ref=None))
    s.commit()
    from app.services.referral_codes import issue_code
    _ANDI_CODE[0] = issue_code(s, "member-andi")
    s.commit()
    s.close()
    app = FastAPI()

    def get_db():
        d = S()
        try:
            yield d
        finally:
            d.close()

    register_business_interest_routes(app, get_db)
    return TestClient(app)


def test_http_requires_matching_checkbox(client):
    body = {"referral_code": _ANDI_CODE[0], "name": "T", "email": "t@example.com",
            "notice_version": "v1.0", "consent_business_interest": True,
            "consent_business_matching": False, "event_id": "h-1"}
    r = client.post("/v1/inbound/business-interest", json=body)
    assert r.status_code == 422
    assert r.json()["detail"]["status"] == "REJECTED_CONSENT"


def test_http_success_with_matching_and_followup_optional(client):
    body = {"referral_code": _ANDI_CODE[0], "name": "T", "email": "t@example.com",
            "notice_version": "v1.0", "consent_business_interest": True,
            "consent_business_matching": True, "consent_business_followup": False, "event_id": "h-2"}
    r = client.post("/v1/inbound/business-interest", json=body)
    assert r.status_code == 200, r.text
    assert r.json()["status"] == "PERSISTED"
