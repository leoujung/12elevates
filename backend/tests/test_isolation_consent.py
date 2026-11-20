import pytest
from sqlalchemy import create_engine, select
from sqlalchemy.orm import sessionmaker

from app.models.core import AuditLog, Base, ConsentRecord, Member, Organization, Prospect
from app.services.prospects import (
    ConsentRequired,
    get_prospect_for_member,
    ingest_prospect,
    list_prospects_for_member,
)


@pytest.fixture()
def db():
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    Session = sessionmaker(bind=engine)
    session = Session()
    org = Organization(name="12ELEVATE test org")
    session.add(org)
    session.flush()
    session.add_all([
        Member(id="member-andi", organization_id=org.id, email="andi@example.test", display_name="Andi"),
        Member(id="member-budi", organization_id=org.id, email="budi@example.test", display_name="Budi"),
    ])
    session.commit()
    yield session
    session.close()


def test_prospect_without_consent_is_rejected(db):
    with pytest.raises(ConsentRequired):
        ingest_prospect(db, owner_member_id="member-andi", name="Sari", source="assessment",
                        consent_purpose=None, consent_granted=False)
    assert db.execute(select(Prospect)).scalars().all() == []


def test_consent_denied_is_rejected(db):
    with pytest.raises(ConsentRequired):
        ingest_prospect(db, owner_member_id="member-andi", name="Sari", source="assessment",
                        consent_purpose="follow_up", consent_granted=False)
    assert db.execute(select(Prospect)).scalars().all() == []


def test_consented_prospect_is_stored_with_consent_and_audit(db):
    p = ingest_prospect(db, owner_member_id="member-andi", name="Sari", source="webinar",
                        consent_purpose="follow_up", consent_granted=True)
    assert db.execute(select(ConsentRecord).where(ConsentRecord.prospect_id == p.id)).scalar_one().purpose == "follow_up"
    audit = db.execute(select(AuditLog).where(AuditLog.target == p.id)).scalar_one()
    assert audit.action == "prospect.created" and audit.actor_member_id == "member-andi"


def test_member_cannot_read_another_members_prospect(db):
    p = ingest_prospect(db, owner_member_id="member-andi", name="Sari", source="webinar",
                        consent_purpose="follow_up", consent_granted=True)
    assert get_prospect_for_member(db, member_id="member-andi", prospect_id=p.id) is not None
    # Budi must get None, not an error that reveals the record exists
    assert get_prospect_for_member(db, member_id="member-budi", prospect_id=p.id) is None


def test_member_list_contains_only_own_prospects(db):
    ingest_prospect(db, owner_member_id="member-andi", name="Sari", source="webinar",
                    consent_purpose="follow_up", consent_granted=True)
    ingest_prospect(db, owner_member_id="member-budi", name="Rina", source="assessment",
                    consent_purpose="follow_up", consent_granted=True)
    andi = list_prospects_for_member(db, member_id="member-andi")
    budi = list_prospects_for_member(db, member_id="member-budi")
    assert [p.name for p in andi] == ["Sari"]
    assert [p.name for p in budi] == ["Rina"]
