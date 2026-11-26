"""E1.2 tests: Central Prospect inbound persistence. SQLite in-memory mirrors the cp_* schema (staging only).

Covers the approved matrix items that can be verified offline:
validation, consent-purpose rules, normalization, dedup (tenant-scoped), idempotency,
suppression, transactional rollback on DB failure, and sync-queue creation only after commit.
"""
import uuid

import pytest
from sqlalchemy import create_engine, event
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.services import central_prospect as cp
from app.services.central_prospect import InboundError, persist_inbound, validate_event, normalize_phone, normalize_email

SCHEMA = [
    "create table suppression_list (id text primary key, identifier text unique not null, kind text not null, source text, created_at text)",
    "create table cp_prospects (prospect_id text primary key, member_id text not null, prospect_type text not null, display_name text, status text not null default 'active', created_at text, updated_at text)",
    "create table cp_prospect_identifiers (id text primary key, prospect_id text not null, member_id text not null, kind text not null, value_normalized text not null, created_at text, unique (member_id, kind, value_normalized))",
    "create table cp_inbound_events (event_id text not null, event_type text not null, member_id text not null, prospect_id text, status text not null, payload_minimal text, received_at text, primary key (member_id, event_id))",
    "create table cp_consent_ledger (id integer primary key autoincrement, prospect_id text not null, member_id text not null, purpose text not null, granted integer not null, notice_version text not null, source text not null, event_id text, recorded_at text, foreign key (member_id, event_id) references cp_inbound_events(member_id, event_id))",
    "create table cp_provenance (prospect_id text primary key, member_id text not null, source_page text, campaign text, referral_code text, first_event_id text, first_seen_at text, foreign key (member_id, first_event_id) references cp_inbound_events(member_id, event_id))",
    "create table cp_sync_queue (id integer primary key autoincrement, prospect_id text not null, member_id text not null, event_id text, destination text not null, idempotency_key text not null, status text not null default 'pending', attempts integer not null default 0, next_attempt_at text, last_error_code text, created_at text, updated_at text, unique (member_id, idempotency_key), foreign key (member_id, event_id) references cp_inbound_events(member_id, event_id))",
    "create table cp_audit_log (id integer primary key autoincrement, member_id text, actor text not null, action text not null, target_id text, reason text, at text)",
]


@pytest.fixture()
def db():
    engine = create_engine("sqlite:///:memory:", poolclass=StaticPool, connect_args={"check_same_thread": False})
    with engine.begin() as c:
        for stmt in SCHEMA:
            c.exec_driver_sql(stmt)
    s = sessionmaker(bind=engine)()
    yield s
    s.close()


def ev(**over):
    base = {
        "event_type": "WEBINAR_REGISTERED",
        "event_id": f"EVT-{uuid.uuid4().hex[:10]}",
        "member_id": "ptn_test_01",
        "lead": {"name": "Uji Satu", "whatsapp": "081211110001", "email": "uji1@example.test"},
        "consents": {"registration_processing": True, "marketing_optional": False},
        "notice_version": "v0-draft",
        "attribution": {"source": "join.html", "campaign": "masterclass-2026"},
    }
    base.update(over)
    return base


def count(db, table):
    return db.execute(cp.text(f"select count(*) from {table}")).scalar()


# --- validation (no writes) ---

@pytest.mark.parametrize("bad,code", [
    ({"event_type": "UNKNOWN"}, "UNKNOWN_EVENT_TYPE"),
    ({"event_id": ""}, "INVALID_EVENT_ID"),
    ({"member_id": ""}, "INVALID_MEMBER"),
    ({"lead": {"whatsapp": "abc", "email": ""}}, "NO_VALID_IDENTIFIER"),
    ({"consents": {"registration_processing": False}}, "REJECTED_CONSENT"),
    ({"consents": {"unknown_purpose": True, "registration_processing": True}}, "UNKNOWN_CONSENT_PURPOSE"),
    ({"consents": {"registration_processing": "yes"}}, "INVALID_CONSENT_VALUE"),
    ({"notice_version": ""}, "INVALID_NOTICE_VERSION"),
])
def test_validation_rejects_before_any_write(db, bad, code):
    with pytest.raises(InboundError) as e:
        persist_inbound(db, ev(**bad))
    assert e.value.code == code
    assert count(db, "cp_inbound_events") == 0
    assert count(db, "cp_sync_queue") == 0


def test_each_event_requires_its_own_purpose():
    # Marketing alone must NOT satisfy a registration event.
    with pytest.raises(InboundError) as e:
        validate_event(ev(event_type="WEBINAR_REGISTERED", consents={"marketing_optional": True}))
    assert e.value.code == "REJECTED_CONSENT"
    # Assessment requires assessment_processing, not registration_processing.
    with pytest.raises(InboundError):
        validate_event(ev(event_type="ASSESSMENT_COMPLETED", consents={"registration_processing": True}))
    # Partner inquiry requires partner_contact.
    ok = validate_event(ev(event_type="PARTNER_INQUIRY", consents={"partner_contact": True}))
    assert ok["event_type"] == "PARTNER_INQUIRY"


# --- normalization ---

def test_phone_and_email_normalization():
    assert normalize_phone("0812-1111-0001") == "6281211110001"
    assert normalize_phone("+62 812 1111 0001") == "6281211110001"
    assert normalize_phone("123") is None
    assert normalize_email("  Uji@Example.TEST ") == "uji@example.test"
    assert normalize_email("bukan-email") is None


# --- persistence, dedup, idempotency ---

def test_persists_prospect_identifiers_consent_provenance_and_queue(db):
    r = persist_inbound(db, ev())
    assert r["status"] == "PERSISTED"
    assert count(db, "cp_prospects") == 1
    assert count(db, "cp_prospect_identifiers") == 2          # phone + email
    assert count(db, "cp_consent_ledger") == 2                # both purposes recorded (granted true AND false)
    assert count(db, "cp_provenance") == 1
    assert count(db, "cp_sync_queue") == 1
    assert count(db, "cp_audit_log") == 1


def test_same_event_id_is_idempotent(db):
    e = ev(event_id="EVT-SAME-1")
    assert persist_inbound(db, e)["status"] == "PERSISTED"
    assert persist_inbound(db, e)["status"] == "DUPLICATE_IGNORED"
    assert count(db, "cp_inbound_events") == 1
    assert count(db, "cp_sync_queue") == 1                    # no second CRM row


def test_dedup_is_tenant_scoped_same_identity_different_members(db):
    a = persist_inbound(db, ev(member_id="ptn_A", event_id="EVT-A1"))
    b = persist_inbound(db, ev(member_id="ptn_B", event_id="EVT-B1"))
    assert a["prospect_id"] != b["prospect_id"]
    assert count(db, "cp_prospects") == 2


def test_same_member_same_phone_reuses_prospect(db):
    a = persist_inbound(db, ev(event_id="EVT-1"))
    b = persist_inbound(db, ev(event_id="EVT-2", event_type="ASSESSMENT_COMPLETED",
                               consents={"assessment_processing": True}))
    assert a["prospect_id"] == b["prospect_id"]
    assert count(db, "cp_prospects") == 1
    assert count(db, "cp_inbound_events") == 2


def test_provenance_keeps_first_seen_only(db):
    a = persist_inbound(db, ev(event_id="EVT-P1", attribution={"source": "first_page"}))
    persist_inbound(db, ev(event_id="EVT-P2", attribution={"source": "second_page"}))
    assert count(db, "cp_provenance") == 1
    first = db.execute(cp.text("select first_event_id from cp_provenance")).scalar()
    assert first == "EVT-P1"


# --- suppression ---

def test_suppressed_identity_is_not_persisted_or_queued(db):
    db.execute(cp.text("insert into suppression_list (id, identifier, kind, source) values ('x','6281211110001','phone','optout')"))
    db.commit()
    r = persist_inbound(db, ev(event_id="EVT-SUP"))
    assert r["status"] == "SUPPRESSED_NO_ACTION"
    assert count(db, "cp_prospects") == 0
    assert count(db, "cp_sync_queue") == 0
    assert count(db, "cp_inbound_events") == 0


# --- transactional safety ---

def test_db_failure_rolls_back_everything_and_enqueues_nothing(db):
    # Force a failure at the consent insert, which happens AFTER prospect rows exist in the same transaction.
    db.execute(cp.text("drop table cp_consent_ledger"))
    db.commit()
    with pytest.raises(Exception):
        persist_inbound(db, ev(event_id="EVT-FAIL"))
    db.rollback()
    assert count(db, "cp_prospects") == 0
    assert count(db, "cp_prospect_identifiers") == 0
    assert count(db, "cp_inbound_events") == 0
    assert count(db, "cp_sync_queue") == 0


def test_queue_row_only_exists_together_with_prospect(db):
    persist_inbound(db, ev(event_id="EVT-Q1"))
    orphan = db.execute(cp.text(
        "select count(*) from cp_sync_queue q left join cp_prospects p on p.prospect_id = q.prospect_id where p.prospect_id is null"
    )).scalar()
    assert orphan == 0
