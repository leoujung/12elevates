"""Tests for the NBI business matching job (deterministic gates, no production DB)."""
import uuid
import pytest
from sqlalchemy import create_engine, text
from sqlalchemy.orm import sessionmaker

from app.services import nbi_matching as nm
from app.services import nbi_matching_job as job


@pytest.fixture()
def db():
    eng = create_engine("sqlite:///:memory:")
    # SQLite has no now(); register it so the SAME SQL runs as in production.
    from sqlalchemy import event

    @event.listens_for(eng, "connect")
    def _register_now(dbapi_conn, _rec):
        dbapi_conn.create_function("now", 0, lambda: "2026-11-27T00:00:00")

    with eng.begin() as c:
        c.execute(text("create table cp_prospects (prospect_id text primary key, member_id text, prospect_type text, display_name text, status text)"))
        c.execute(text("create table cp_provenance (prospect_id text primary key, member_id text, referral_code text, first_seen_at text)"))
        c.execute(text("create table cp_consent_ledger (id integer primary key autoincrement, prospect_id text, member_id text, purpose text, granted integer, recorded_at text)"))
        c.execute(text("create table member_target_tags (member_id text, tag text, created_at text, primary key (member_id, tag))"))
        c.execute(text("create table cp_prospect_tags (prospect_id text, member_id text, tag text, created_at text, primary key (prospect_id, tag))"))
        c.execute(text("create table nbi_discovery_jobs (id text primary key, member_id text, pathway text, source_key text, is_synthetic integer, status text, created_at text, finished_at text)"))
        c.execute(text("create table nbi_matching_results (id text primary key, job_id text, member_id text, prospect_id text, fit_score integer, intent_confidence integer, data_confidence integer, reason text, rules_version text, is_synthetic integer, created_at text)"))
    s = sessionmaker(bind=eng)()
    yield s
    s.close()


def _prospect(db, member="m1", name="A", referral="REF1", granted=True):
    pid = str(uuid.uuid4())
    db.execute(text("insert into cp_prospects values (:p,:m,'business',:n,'active')"), {"p": pid, "m": member, "n": name})
    db.execute(text("insert into cp_provenance values (:p,:m,:r,'2026-11-27T00:00:00')"), {"p": pid, "m": member, "r": referral})
    if granted is not None:
        db.execute(text("insert into cp_consent_ledger (prospect_id,member_id,purpose,granted,recorded_at) values (:p,:m,'business_matching',:g,'2026-11-27T00:00:00')"),
                   {"p": pid, "m": member, "g": 1 if granted else 0})
    return pid


def test_no_consent_is_rejected_and_not_scored(db):
    _prospect(db, granted=False)
    out = job.run_business_job(db, "m1")
    assert out["rejected_no_consent"] == 1 and out["scored"] == 0


def test_no_consent_row_at_all_is_rejected(db):
    _prospect(db, granted=None)
    out = job.run_business_job(db, "m1")
    assert out["rejected_no_consent"] == 1


def test_unverified_source_without_referral_is_quarantined(db):
    _prospect(db, referral=None)
    out = job.run_business_job(db, "m1")
    assert out["quarantined_unverified_source"] == 1 and out["scored"] == 0


def test_verified_referral_with_consent_is_scored_with_no_tags_fit_zero(db):
    _prospect(db)
    out = job.run_business_job(db, "m1")
    rows = db.execute(text("select fit_score, intent_confidence, data_confidence, reason, is_synthetic from nbi_matching_results")).all()
    assert len(rows) == 1
    fit, intent, data, reason, synth = rows[0]
    assert fit == 0                      # no target tags -> no basis to fit (never invented)
    assert "no member target tags declared" in reason
    assert intent > 0                    # explicit_inquiry signal
    assert synth == 0                    # written as real, not synthetic


def test_scores_stay_separate_never_combined_into_one_rank(db):
    _prospect(db)
    job.run_business_job(db, "m1")
    row = db.execute(text("select fit_score, intent_confidence, data_confidence from nbi_matching_results")).one()
    assert None not in row
    assert not hasattr(nm, "overall_score") and not hasattr(nm, "rank")


def test_job_status_is_done_not_finished(db):
    _prospect(db)
    out = job.run_business_job(db, "m1")
    status = db.execute(text("select status from nbi_discovery_jobs where id=:id"), {"id": out["job_id"]}).scalar()
    assert status == "done"


def test_other_member_prospects_are_not_read(db):
    _prospect(db, member="m1")
    _prospect(db, member="m2", name="B")
    out = job.run_business_job(db, "m1")
    assert out["prospects"] == 1


def test_health_fields_never_reach_business_pathway():
    rec = {"name": "x", "source_key": "referral", "source_verified": True, "consent_granted": True,
           "consent_record_id": "c1", "assessment_score": 80, "tags": [], "signals": {}}
    res = nm.evaluate(rec, {"target_tags": []}, "business")
    assert res["status"] == "rejected_sensitive_field"
