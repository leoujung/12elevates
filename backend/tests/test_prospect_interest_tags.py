"""Tests: prospect interest tags (closed list) flow from intake to the matching job."""
import uuid
import pytest
from sqlalchemy import create_engine, event, text
from sqlalchemy.orm import sessionmaker

from app.services import central_prospect as cp
from app.services import nbi_matching_job as job


@pytest.fixture()
def db():
    eng = create_engine("sqlite:///:memory:")

    @event.listens_for(eng, "connect")
    def _now(dbapi_conn, _rec):
        dbapi_conn.create_function("now", 0, lambda: "2026-11-27T00:00:00")

    with eng.begin() as c:
        c.execute(text("create table suppression_list (id text primary key, identifier text unique not null, kind text not null, source text, created_at text)"))
        c.execute(text("create table cp_prospects (prospect_id text primary key, member_id text not null, prospect_type text not null, display_name text, status text not null default 'active', created_at text, updated_at text)"))
        c.execute(text("create table cp_prospect_identifiers (id text primary key, prospect_id text not null, member_id text not null, kind text not null, value_normalized text not null, created_at text, unique (member_id, kind, value_normalized))"))
        c.execute(text("create table cp_inbound_events (event_id text not null, event_type text not null, member_id text not null, prospect_id text, status text not null, payload_minimal text, received_at text, primary key (member_id, event_id))"))
        c.execute(text("create table cp_consent_ledger (id integer primary key autoincrement, prospect_id text not null, member_id text not null, purpose text not null, granted integer not null, notice_version text not null, source text not null, event_id text, recorded_at text, foreign key (member_id, event_id) references cp_inbound_events(member_id, event_id))"))
        c.execute(text("create table cp_provenance (prospect_id text primary key, member_id text not null, source_page text, campaign text, referral_code text, first_event_id text, first_seen_at text, foreign key (member_id, first_event_id) references cp_inbound_events(member_id, event_id))"))
        c.execute(text("create table cp_sync_queue (id integer primary key autoincrement, prospect_id text not null, member_id text not null, event_id text, destination text not null, idempotency_key text not null, status text not null default 'pending', attempts integer not null default 0, next_attempt_at text, last_error_code text, created_at text, updated_at text, unique (member_id, idempotency_key), foreign key (member_id, event_id) references cp_inbound_events(member_id, event_id))"))
        c.execute(text("create table cp_audit_log (id integer primary key autoincrement, member_id text, actor text not null, action text not null, target_id text, reason text, at text)"))
        c.execute(text("create table member_target_tags (member_id text, tag text, created_at text, primary key (member_id, tag))"))
        c.execute(text("create table cp_prospect_tags (prospect_id text, member_id text, tag text, created_at text, primary key (prospect_id, tag))"))
        c.execute(text("create table nbi_discovery_jobs (id text primary key, member_id text, pathway text, source_key text, is_synthetic integer, status text, created_at text, finished_at text)"))
        c.execute(text("create table nbi_matching_results (id text primary key, job_id text, member_id text, prospect_id text, fit_score integer, intent_confidence integer, data_confidence integer, reason text, rules_version text, is_synthetic integer, created_at text)"))
    s = sessionmaker(bind=eng)()
    yield s
    s.close()


def _event(**over):
    e = {
        "event_type": "BUSINESS_INTEREST",
        "event_id": str(uuid.uuid4()),
        "member_id": "m1",
        "lead": {"name": "A", "email": "a@example.invalid"},
        "consents": {"business_interest_processing": True, "business_matching": True, "business_followup": True},
        "notice_version": "1.2",
        "attribution": {"source": "business_form", "referral_code": "REF1"},
    }
    e.update(over)
    return e


def test_unknown_interest_tag_is_rejected_before_any_write(db):
    with pytest.raises(cp.InboundError) as ex:
        cp.persist_inbound(db, _event(interest_tags=["consultant", "my health condition"]))
    assert ex.value.code == "INVALID_INTEREST_TAG"
    assert db.execute(text("select count(*) from cp_prospects")).scalar() == 0


def test_too_many_tags_rejected(db):
    with pytest.raises(cp.InboundError) as ex:
        cp.persist_inbound(db, _event(interest_tags=["consultant"] * 11))
    assert ex.value.code == "INVALID_INTEREST_TAG"


def test_valid_tags_are_stored_normalized_and_deduped(db):
    r = cp.persist_inbound(db, _event(interest_tags=[" Consultant ", "consultant", "startup"]))
    assert r["status"] == "PERSISTED"
    tags = [t for (t,) in db.execute(text("select tag from cp_prospect_tags order by tag")).all()]
    assert tags == ["consultant", "startup"]


def test_tags_are_optional(db):
    r = cp.persist_inbound(db, _event())
    assert r["status"] == "PERSISTED"
    assert db.execute(text("select count(*) from cp_prospect_tags")).scalar() == 0


def test_job_fit_uses_prospect_tags_overlap_with_member_tags(db):
    db.execute(text("insert into member_target_tags values ('m1','consultant','2026-11-27')"))
    cp.persist_inbound(db, _event(interest_tags=["consultant"]))
    out = job.run_business_job(db, "m1")
    reason = db.execute(text("select reason from nbi_matching_results")).scalar()
    assert out["scored"] == 1
    assert "matched target tag: consultant" in reason


def test_no_overlap_gives_fit_zero_with_honest_reason(db):
    db.execute(text("insert into member_target_tags values ('m1','consultant','2026-11-27')"))
    cp.persist_inbound(db, _event(interest_tags=["startup"]))
    job.run_business_job(db, "m1")
    reason = db.execute(text("select reason from nbi_matching_results")).scalar()
    assert "no overlap between member targets and prospect tags" in reason


def test_prospect_without_tags_still_fit_zero(db):
    db.execute(text("insert into member_target_tags values ('m1','consultant','2026-11-27')"))
    cp.persist_inbound(db, _event())
    job.run_business_job(db, "m1")
    fit = db.execute(text("select fit_score from nbi_matching_results")).scalar()
    assert fit == 0
