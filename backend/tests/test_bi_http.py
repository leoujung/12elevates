import os
import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, text
from sqlalchemy.pool import StaticPool
from sqlalchemy.orm import sessionmaker
from app.models.core import Base, Member, Organization
from app.api.v1.business_interest import register_business_interest_routes

@pytest.fixture()
def client():
    engine = create_engine("sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool)
    Base.metadata.create_all(engine)
    with engine.begin() as c:
        c.execute(text("create table if not exists suppression_list (identifier text primary key)"))
        c.execute(text("create table if not exists cp_prospects (prospect_id text primary key, member_id text, prospect_type text, display_name text, status text, created_at text, updated_at text)"))
        c.execute(text("create table if not exists cp_prospect_identifiers (id text primary key, prospect_id text, member_id text, kind text, value_normalized text, created_at text)"))
        c.execute(text("create table if not exists cp_inbound_events (event_id text, event_type text, member_id text, prospect_id text, status text, payload_minimal text, received_at text)"))
        c.execute(text("create table if not exists cp_consent_ledger (prospect_id text, member_id text, purpose text, granted boolean, notice_version text, source text, event_id text, recorded_at text)"))
        c.execute(text("create table if not exists cp_provenance (prospect_id text, member_id text, source_page text, campaign text, referral_code text, first_event_id text, first_seen_at text)"))
        c.execute(text("create table if not exists cp_sync_queue (prospect_id text, member_id text, event_id text, destination text, idempotency_key text, status text, attempts int, next_attempt_at text, created_at text, updated_at text)"))
        c.execute(text("create table if not exists cp_audit_log (member_id text, actor text, action text, target_id text, reason text, at text)"))
    S = sessionmaker(bind=engine)
    s = S()
    org = Organization(name="t")
    s.add(org); s.flush()
    s.add(Member(id="member-andi", organization_id=org.id, email="andi@example.test",
                 display_name="Andi", sponsor_ref="REF-ANDI-01"))
    s.commit(); s.close()
    app = FastAPI()
    def get_db():
        d = S()
        try: yield d
        finally: d.close()
    register_business_interest_routes(app, get_db)
    return TestClient(app)

BASE = {"referral_code": "REF-ANDI-01", "name": "Tester", "email": "tester@example.com",
        "notice_version": "v-draft", "consent_business_interest": True, "event_id": "bi-http-1"}

def test_no_referral_rejected(client):
    body = dict(BASE); body["referral_code"] = ""
    r = client.post("/v1/inbound/business-interest", json=body)
    assert r.status_code == 422

def test_unknown_referral_rejected(client):
    body = dict(BASE); body["referral_code"] = "REF-FAKE"
    r = client.post("/v1/inbound/business-interest", json=body)
    assert r.status_code == 422
    assert r.json()["detail"]["status"] == "INVALID_REFERRAL"

def test_missing_consent_rejected(client):
    body = dict(BASE); body["consent_business_interest"] = False
    r = client.post("/v1/inbound/business-interest", json=body)
    assert r.status_code == 422
    assert r.json()["detail"]["status"] == "REJECTED_CONSENT"

def test_valid_referral_persists_to_referrer(client):
    r = client.post("/v1/inbound/business-interest", json=BASE)
    assert r.status_code == 200, r.text
    assert r.json()["status"] == "PERSISTED"

def test_unknown_field_rejected(client):
    body = dict(BASE); body["owner"] = "someone"
    r = client.post("/v1/inbound/business-interest", json=body)
    assert r.status_code == 422
