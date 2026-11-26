"""Referral codes: issue per member, revoke on reissue, resolve for intake."""
import pytest
from sqlalchemy import create_engine, text
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.models.core import Base
from app.services import referral_codes as rc


@pytest.fixture()
def db():
    engine = create_engine("sqlite://", connect_args={"check_same_thread": False},
                           poolclass=StaticPool)
    Base.metadata.create_all(engine)
    # member_referral_codes is created by migration h1i2refcodes01 (raw DDL here for SQLite)
    with engine.begin() as c:
        c.execute(text("""create table if not exists member_referral_codes (
            code varchar(40) primary key, member_id varchar(64) not null,
            created_at datetime default current_timestamp, revoked_at datetime)"""))
    s = sessionmaker(bind=engine)()
    from app.models.core import Organization, Member
    org = Organization(name="t")
    s.add(org); s.flush()
    for mid in ["member-a", "member-b"]:
        s.add(Member(id=mid, organization_id=org.id, email=f"{mid}@example.test", display_name=mid))
    s.commit()
    yield s
    s.close()


def test_issue_returns_random_code_for_member(db):
    code = rc.issue_code(db, "member-a")
    db.commit()
    assert len(code) >= 10
    assert rc.resolve_code(db, code) == "member-a"


def test_reissue_revokes_previous_code(db):
    old = rc.issue_code(db, "member-a")
    db.commit()
    new = rc.issue_code(db, "member-a")
    db.commit()
    assert old != new
    assert rc.resolve_code(db, old) is None
    assert rc.resolve_code(db, new) == "member-a"


def test_unknown_or_empty_code_resolves_to_none(db):
    assert rc.resolve_code(db, "") is None
    assert rc.resolve_code(db, "NOPE") is None
    assert rc.resolve_code(db, "x" * 101) is None


def test_codes_are_per_member(db):
    a = rc.issue_code(db, "member-a")
    b = rc.issue_code(db, "member-b")
    db.commit()
    assert rc.resolve_code(db, a) == "member-a"
    assert rc.resolve_code(db, b) == "member-b"


def test_sponsor_ref_not_used_for_intake(db, monkeypatch):
    # members.sponsor_ref must NOT act as a referral source anymore.
    from app.api.v1 import business_interest as bi
    db.execute(text("create table if not exists members (id varchar(64) primary key, sponsor_ref varchar(100))"))
    db.execute(text("insert into members (id, sponsor_ref) values ('m1', 'OLD-SPONSOR')"))
    db.commit()
    assert bi._resolve_referrer(db, "OLD-SPONSOR") is None
