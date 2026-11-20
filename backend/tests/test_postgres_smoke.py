"""Postgres smoke test: re-runs the core isolation and consent rules on real PostgreSQL.

Skipped unless APP_TEST_DATABASE_URL is set, e.g.
  postgresql+psycopg://<user>:<password-from-env>@<host>:<port>/<test_db>
The URL is read from the environment and is never printed.
"""
import os

import pytest
from sqlalchemy import select
from sqlalchemy.orm import sessionmaker

from app.models.core import Base, Member, Organization, Prospect
from app.services.prospects import ConsentRequired, get_prospect_for_member, ingest_prospect

URL = os.environ.get("APP_TEST_DATABASE_URL")
pytestmark = pytest.mark.skipif(not URL, reason="APP_TEST_DATABASE_URL not set")


@pytest.fixture()
def db():
    from sqlalchemy import create_engine
    engine = create_engine(URL)
    Base.metadata.drop_all(engine)
    Base.metadata.create_all(engine)
    Session = sessionmaker(bind=engine)
    s = Session()
    org = Organization(name="pg test org")
    s.add(org)
    s.flush()
    s.add_all([
        Member(id="member-andi", organization_id=org.id, email="andi@pg.test", display_name="Andi"),
        Member(id="member-budi", organization_id=org.id, email="budi@pg.test", display_name="Budi"),
    ])
    s.commit()
    yield s
    s.close()
    Base.metadata.drop_all(engine)
    engine.dispose()


def test_pg_consent_required(db):
    with pytest.raises(ConsentRequired):
        ingest_prospect(db, owner_member_id="member-andi", name="Sari", source="assessment",
                        consent_purpose=None, consent_granted=False)
    assert db.execute(select(Prospect)).scalars().all() == []


def test_pg_cross_member_isolation(db):
    p = ingest_prospect(db, owner_member_id="member-andi", name="Sari", source="webinar",
                        consent_purpose="follow_up", consent_granted=True)
    assert get_prospect_for_member(db, member_id="member-andi", prospect_id=p.id) is not None
    assert get_prospect_for_member(db, member_id="member-budi", prospect_id=p.id) is None
