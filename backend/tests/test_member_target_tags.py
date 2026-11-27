"""Tests: member target tags (closed list, validation, isolation) and job reads them."""
import uuid
import pytest
from sqlalchemy import create_engine, event, text
from sqlalchemy.orm import sessionmaker

from app.services import member_target_tags as mtt
from app.services import nbi_matching_job as job


@pytest.fixture()
def db():
    eng = create_engine("sqlite:///:memory:")

    @event.listens_for(eng, "connect")
    def _now(dbapi_conn, _rec):
        dbapi_conn.create_function("now", 0, lambda: "2026-11-27T00:00:00")

    with eng.begin() as c:
        c.execute(text("create table member_target_tags (member_id text, tag text, created_at text, primary key (member_id, tag))"))
        c.execute(text("create table cp_prospect_tags (prospect_id text, member_id text, tag text, created_at text, primary key (prospect_id, tag))"))
        c.execute(text("create table cp_prospects (prospect_id text primary key, member_id text, prospect_type text, display_name text, status text)"))
        c.execute(text("create table cp_provenance (prospect_id text primary key, member_id text, referral_code text, first_seen_at text)"))
        c.execute(text("create table cp_consent_ledger (id integer primary key autoincrement, prospect_id text, member_id text, purpose text, granted integer, recorded_at text)"))
        c.execute(text("create table nbi_discovery_jobs (id text primary key, member_id text, pathway text, source_key text, is_synthetic integer, status text, created_at text, finished_at text)"))
        c.execute(text("create table nbi_matching_results (id text primary key, job_id text, member_id text, prospect_id text, fit_score integer, intent_confidence integer, data_confidence integer, reason text, rules_version text, is_synthetic integer, created_at text)"))
    s = sessionmaker(bind=eng)()
    yield s
    s.close()


def test_set_and_get_tags_normalized_and_deduped(db):
    saved = mtt.set_tags(db, "m1", [" Consultant ", "consultant", "startup"])
    assert saved == ["consultant", "startup"]
    assert mtt.get_tags(db, "m1") == ["consultant", "startup"]


def test_unknown_tag_rejected_no_free_text(db):
    with pytest.raises(ValueError, match="unknown_tag"):
        mtt.set_tags(db, "m1", ["consultant", "my health condition"])
    assert mtt.get_tags(db, "m1") == []


def test_too_many_tags_rejected(db):
    many = sorted(mtt.ALLOWED_TAGS)[: mtt.MAX_TAGS + 1]
    with pytest.raises(ValueError, match="too_many_tags"):
        mtt.set_tags(db, "m1", many)


def test_replace_semantics_clear_with_empty_list(db):
    mtt.set_tags(db, "m1", ["consultant"])
    mtt.set_tags(db, "m1", [])
    assert mtt.get_tags(db, "m1") == []


def test_tags_are_isolated_per_member(db):
    mtt.set_tags(db, "m1", ["consultant"])
    mtt.set_tags(db, "m2", ["startup"])
    assert mtt.get_tags(db, "m1") == ["consultant"]
    assert mtt.get_tags(db, "m2") == ["startup"]


def test_job_uses_member_tags_for_fit_not_invented(db):
    # Prospect with referral + consent; member declared tags -> job reads them.
    pid = str(uuid.uuid4())
    db.execute(text("insert into cp_prospects values (:p,'m1','business','A','active')"), {"p": pid})
    db.execute(text("insert into cp_provenance values (:p,'m1','REF1','2026-11-27T00:00:00')"), {"p": pid})
    db.execute(text("insert into cp_consent_ledger (prospect_id,member_id,purpose,granted,recorded_at) values (:p,'m1','business_matching',1,'2026-11-27T00:00:00')"), {"p": pid})
    mtt.set_tags(db, "m1", ["consultant"])
    out = job.run_business_job(db, "m1")
    reason = db.execute(text("select reason from nbi_matching_results")).scalar()
    assert out["scored"] == 1
    assert "no member target tags declared" not in reason  # tags were read, not treated as empty
