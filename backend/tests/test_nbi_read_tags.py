"""Tests: /v1/nbi/results returns interest_tags, scoped to the token's member only."""
import uuid
from sqlalchemy import create_engine, event, text
from sqlalchemy.orm import sessionmaker

from app.api.v1 import nbi_read


def _db():
    eng = create_engine("sqlite:///:memory:")

    @event.listens_for(eng, "connect")
    def _now(dbapi_conn, _rec):
        dbapi_conn.create_function("now", 0, lambda: "2026-11-27T00:00:00")

    with eng.begin() as c:
        c.execute(text("create table nbi_matching_results (id text primary key, job_id text, member_id text, prospect_id text, fit_score integer, intent_confidence integer, data_confidence integer, reason text, rules_version text, is_synthetic integer, created_at text)"))
        c.execute(text("create table cp_prospect_tags (prospect_id text, member_id text, tag text, created_at text, primary key (prospect_id, tag))"))
    return sessionmaker(bind=eng)()


def _call(db, member):
    # Call the route handler directly, with the same member scoping the token would give.
    captured = {}

    class _App:
        def get(self, path):
            def deco(fn):
                captured["fn"] = fn
                return fn
            return deco

    nbi_read.register_nbi_read_routes(_App(), lambda: db, lambda: member)
    return captured["fn"](limit=50, member_id=member, db=db)


def _row(db, member, prospect, fit=0):
    db.execute(text("insert into nbi_matching_results values (:i,'j',:m,:p,:f,50,70,'r','nbi-rules-v1',0,'2026-11-27T00:00:00')"),
               {"i": str(uuid.uuid4()), "m": member, "p": prospect, "f": fit})


def test_tags_attached_to_matching_prospect():
    db = _db()
    p = str(uuid.uuid4())
    _row(db, "m1", p, 100)
    db.execute(text("insert into cp_prospect_tags values (:p,'m1','consultant','2026-11-27')"), {"p": p})
    db.execute(text("insert into cp_prospect_tags values (:p,'m1','startup','2026-11-27')"), {"p": p})
    out = _call(db, "m1")
    assert out["items"][0]["interest_tags"] == ["consultant", "startup"]


def test_prospect_without_tags_gets_empty_list():
    db = _db()
    _row(db, "m1", str(uuid.uuid4()), 0)
    out = _call(db, "m1")
    assert out["items"][0]["interest_tags"] == []


def test_tags_of_another_member_never_leak():
    db = _db()
    p = str(uuid.uuid4())
    _row(db, "m1", p, 0)
    # Same prospect id, but tags written under a different member: must not be shown to m1.
    db.execute(text("insert into cp_prospect_tags values (:p,'m2','secret-other','2026-11-27')"), {"p": p})
    out = _call(db, "m1")
    assert out["items"][0]["interest_tags"] == []


def test_results_still_exclude_synthetic_rows():
    db = _db()
    db.execute(text("insert into nbi_matching_results values ('s1','j','m1',:p,0,50,70,'demo','nbi-rules-v1',1,'2026-11-27T00:00:00')"),
               {"p": str(uuid.uuid4())})
    out = _call(db, "m1")
    assert out["count"] == 0
