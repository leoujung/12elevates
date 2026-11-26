"""Suppression list: normalisation, idempotent write, and persistence across sessions (the original bug)."""
from sqlalchemy import create_engine, text
from sqlalchemy.orm import sessionmaker

from app.services import suppression as sup


def _db():
    eng = create_engine("sqlite:///:memory:")
    with eng.begin() as c:
        c.execute(text("create table suppression_list (id text primary key, identifier text unique not null, "
                       "kind text not null, source text not null, created_at text not null)"))
    return sessionmaker(bind=eng)


def test_normalize_matches_vercel_rules():
    assert sup.normalize("0812-0000-0001") == "081200000001"
    assert sup.normalize("+62 812 0000 0001") == "6281200000001"
    assert sup.normalize("  Andi@Example.TEST ") == "andi@example.test"
    assert sup.normalize("not-an-email@") is None
    assert sup.normalize("") is None
    assert sup.normalize(None) is None


def test_add_then_suppressed():
    S = _db()
    db = S()
    assert sup.add(db, identifier="081200000001", source="optout") is True
    assert sup.is_suppressed(db, "0812-0000-0001") is True


def test_add_is_idempotent():
    S = _db()
    db = S()
    assert sup.add(db, identifier="optout@example.test", source="optout") is True
    assert sup.add(db, identifier="OPTOUT@example.test", source="optout") is False
    rows = db.execute(text("select count(*) from suppression_list")).scalar()
    assert rows == 1


def test_invalid_identifier_is_never_written():
    S = _db()
    db = S()
    assert sup.add(db, identifier="bad@", source="optout") is False
    assert db.execute(text("select count(*) from suppression_list")).scalar() == 0


def test_suppression_survives_new_session_same_db():
    # The original bug: state lived in one process. A new session on the same store must still see it.
    S = _db()
    sup.add(S(), identifier="081200000001", source="optout")
    fresh = S()
    assert sup.is_suppressed(fresh, "081200000001") is True


def test_not_suppressed_by_default():
    S = _db()
    assert sup.is_suppressed(S(), "081299999999") is False
