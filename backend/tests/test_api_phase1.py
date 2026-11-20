import os

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

os.environ.setdefault("APP_JWT_SECRET", "test-only-secret-not-for-production-0123456789")

from app.api.v1.routes import create_app
from app.core.security import hash_password
from app.models.core import Base, Member, Organization


@pytest.fixture()
def client():
    # StaticPool: one shared in-memory DB for the fixture AND the app's sessions.
    # Without it each connection gets its own empty database.
    engine = create_engine("sqlite:///:memory:", connect_args={"check_same_thread": False}, poolclass=StaticPool)
    Base.metadata.create_all(engine)
    Session = sessionmaker(bind=engine)
    s = Session()
    org = Organization(name="test org")
    s.add(org)
    s.flush()
    s.add_all([
        Member(id="member-andi", organization_id=org.id, email="andi@example.test",
               display_name="Andi", password_hash=hash_password("andi-pass-123")),
        Member(id="member-budi", organization_id=org.id, email="budi@example.test",
               display_name="Budi", password_hash=hash_password("budi-pass-456")),
    ])
    s.commit()
    s.close()
    return TestClient(create_app(Session))


def login(client, email, password):
    r = client.post("/v1/auth/login", json={"email": email, "password": password})
    assert r.status_code == 200, r.text
    return {"Authorization": "Bearer " + r.json()["access_token"]}


def test_routes_reject_missing_token(client):
    assert client.get("/v1/prospects").status_code == 401
    assert client.post("/v1/prospects", json={"name": "x", "source": "y", "consent_purpose": "f", "consent_granted": True}).status_code == 401


def test_routes_reject_forged_token(client):
    r = client.get("/v1/prospects", headers={"Authorization": "Bearer not-a-real-token"})
    assert r.status_code == 401


def test_login_wrong_password_and_unknown_email_look_identical(client):
    wrong = client.post("/v1/auth/login", json={"email": "andi@example.test", "password": "nope"})
    unknown = client.post("/v1/auth/login", json={"email": "ghost@example.test", "password": "nope"})
    assert wrong.status_code == unknown.status_code == 401
    assert wrong.json() == unknown.json()


def test_consent_required_over_http(client):
    h = login(client, "andi@example.test", "andi-pass-123")
    r = client.post("/v1/prospects", headers=h, json={"name": "Sari", "source": "webinar"})
    assert r.status_code == 422


def test_create_then_list_only_own(client):
    andi = login(client, "andi@example.test", "andi-pass-123")
    budi = login(client, "budi@example.test", "budi-pass-456")
    assert client.post("/v1/prospects", headers=andi, json={
        "name": "Sari", "source": "webinar", "consent_purpose": "follow_up", "consent_granted": True}).status_code == 201
    assert client.post("/v1/prospects", headers=budi, json={
        "name": "Rina", "source": "assessment", "consent_purpose": "follow_up", "consent_granted": True}).status_code == 201
    andi_names = [p["name"] for p in client.get("/v1/prospects", headers=andi).json()]
    budi_names = [p["name"] for p in client.get("/v1/prospects", headers=budi).json()]
    assert andi_names == ["Sari"]
    assert budi_names == ["Rina"]


def test_cross_member_read_returns_404_not_403(client):
    andi = login(client, "andi@example.test", "andi-pass-123")
    budi = login(client, "budi@example.test", "budi-pass-456")
    pid = client.post("/v1/prospects", headers=andi, json={
        "name": "Sari", "source": "webinar", "consent_purpose": "follow_up", "consent_granted": True}).json()["id"]
    assert client.get(f"/v1/prospects/{pid}", headers=andi).status_code == 200
    # 404 (not 403) so the response does not reveal that the record exists
    assert client.get(f"/v1/prospects/{pid}", headers=budi).status_code == 404


def test_responses_do_not_leak_contact_details(client):
    andi = login(client, "andi@example.test", "andi-pass-123")
    created = client.post("/v1/prospects", headers=andi, json={
        "name": "Sari", "source": "webinar", "consent_purpose": "follow_up", "consent_granted": True,
        "whatsapp": "081234500001", "email": "sari@example.test"}).json()
    body = str(created) + str(client.get("/v1/prospects", headers=andi).json())
    assert "081234500001" not in body
    assert "sari@example.test" not in body
