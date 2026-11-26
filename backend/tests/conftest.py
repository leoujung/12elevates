"""Shared fixtures."""
import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.models.core import Base, Member, Organization


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
