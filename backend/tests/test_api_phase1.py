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


def _admin_seed_lp(client, member_email, points):
    """Seed LP through the admin path. Member self-entry (POST /v1/lp) is disabled (410).

    Creates an admin in the same DB as the client, then records one verified transaction.
    Uses the module-level SQLite session the client was built with.
    """
    from app.models.core import Member
    from app.services import gold_pool_issuance as iss
    import uuid
    session = client.app.state.session_factory()
    try:
        if session.query(Member).filter(Member.email == "seed-admin@example.test").first() is None:
            m = session.query(Member).filter(Member.email == member_email).first()
            session.add(Member(id=str(uuid.uuid4()), organization_id=m.organization_id,
                               email="seed-admin@example.test", display_name="Seed Admin", is_admin=True))
            session.commit()
        iss.record_manual(session, actor_id="seed", member_email=member_email,
                          transaction_id=f"SEED-{member_email}-{points}-{uuid.uuid4()}",
                          tx_type="LOYALTY_ORDER", lp=points, verified_at="2026-11-20T10:00:00+07:00")
    finally:
        session.close()


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


def test_owner_sees_own_contact_but_other_members_never_do(client):
    andi = login(client, "andi@example.test", "andi-pass-123")
    budi = login(client, "budi@example.test", "budi-pass-456")
    created = client.post("/v1/prospects", headers=andi, json={
        "name": "Sari", "source": "webinar", "consent_purpose": "follow_up", "consent_granted": True,
        "whatsapp": "081234500001", "email": "sari@example.test"}).json()
    pid = created["id"]

    # The owner (Andi) can see the contact details -- needed to act on the lead.
    andi_list = client.get("/v1/prospects", headers=andi).json()
    assert andi_list[0]["whatsapp"] == "081234500001"
    assert andi_list[0]["email"] == "sari@example.test"

    # Budi (a different member) never sees Sari at all: not in his own list, and 404 by id.
    budi_list_body = str(client.get("/v1/prospects", headers=budi).json())
    assert "081234500001" not in budi_list_body
    assert "sari@example.test" not in budi_list_body
    assert client.get(f"/v1/prospects/{pid}", headers=budi).status_code == 404


def test_lp_summary_starts_at_zero_and_accumulates(client):
    andi = login(client, "andi@example.test", "andi-pass-123")
    summary = client.get("/v1/lp/summary", headers=andi).json()
    assert summary == {"total_lp": 0, "target_lp": 150, "percent": 0, "qualified": False, "entry_count": 0}

    assert client.post("/v1/lp", headers=andi, json={"points": 50, "note": "pack A"}).status_code == 410
    assert client.post("/v1/lp", headers=andi, json={"points": 100}).status_code == 410
    # Verified LP arrives only through the administrator path.
    _admin_seed_lp(client, "andi@example.test", 50)
    _admin_seed_lp(client, "andi@example.test", 100)
    summary = client.get("/v1/lp/summary", headers=andi).json()
    assert summary["total_lp"] == 150
    assert summary["percent"] == 100
    assert summary["qualified"] is True
    assert summary["entry_count"] == 2


def test_lp_rejects_non_positive_points(client):
    andi = login(client, "andi@example.test", "andi-pass-123")
    assert client.post("/v1/lp", headers=andi, json={"points": 0}).status_code == 410
    assert client.post("/v1/lp", headers=andi, json={"points": -5}).status_code == 410


def test_lp_is_isolated_between_members(client):
    andi = login(client, "andi@example.test", "andi-pass-123")
    budi = login(client, "budi@example.test", "budi-pass-456")
    _admin_seed_lp(client, "andi@example.test", 150)
    andi_summary = client.get("/v1/lp/summary", headers=andi).json()
    budi_summary = client.get("/v1/lp/summary", headers=budi).json()
    assert andi_summary["total_lp"] == 150
    assert budi_summary["total_lp"] == 0  # Budi's summary is unaffected by Andi's entries


def test_habit_today_defaults_empty_and_can_toggle_items(client):
    andi = login(client, "andi@example.test", "andi-pass-123")
    today = client.get("/v1/habit/today", headers=andi).json()
    assert today["completed_count"] == 0
    assert today["total"] == 12
    assert today["core4_done"] is False
    assert len(today["items"]) == 12  # the 12 named Core4 + Power-Ups items are returned

    r = client.put("/v1/habit/today", headers=andi, json={"item_id": 1, "done": True})
    assert r.status_code == 200
    assert r.json()["completed_count"] == 1
    assert 1 in r.json()["completed_ids"]

    # untoggle
    r = client.put("/v1/habit/today", headers=andi, json={"item_id": 1, "done": False})
    assert r.json()["completed_count"] == 0


def test_core4_completion_marks_daily_win(client):
    andi = login(client, "andi@example.test", "andi-pass-123")
    for item_id in [1, 2, 3]:
        client.put("/v1/habit/today", headers=andi, json={"item_id": item_id, "done": True})
    assert client.get("/v1/habit/today", headers=andi).json()["core4_done"] is False
    client.put("/v1/habit/today", headers=andi, json={"item_id": 4, "done": True})
    today = client.get("/v1/habit/today", headers=andi).json()
    assert today["core4_done"] is True
    assert "Daily Win" in today["footer_message"] or "Legend" in today["footer_message"]


def test_habit_rejects_unknown_item_id(client):
    andi = login(client, "andi@example.test", "andi-pass-123")
    assert client.put("/v1/habit/today", headers=andi, json={"item_id": 99, "done": True}).status_code == 422


def test_habit_is_isolated_between_members(client):
    andi = login(client, "andi@example.test", "andi-pass-123")
    budi = login(client, "budi@example.test", "budi-pass-456")
    for item_id in range(1, 13):
        client.put("/v1/habit/today", headers=andi, json={"item_id": item_id, "done": True})
    assert client.get("/v1/habit/today", headers=andi).json()["completed_count"] == 12
    assert client.get("/v1/habit/today", headers=budi).json()["completed_count"] == 0


def test_rest_day_quota_enforced(client):
    andi = login(client, "andi@example.test", "andi-pass-123")
    r = client.post("/v1/habit/rest-day", headers=andi)
    assert r.status_code == 200
    assert r.json()["is_rest_day"] is True
    assert r.json()["rest_days_left_this_month"] == 0
    # quota is 1/month: a second rest day today should be rejected since it's already used
    r2 = client.post("/v1/habit/rest-day", headers=andi)
    assert r2.status_code == 422


def test_consistency_score_returns_7_days(client):
    andi = login(client, "andi@example.test", "andi-pass-123")
    for item_id in range(1, 5):
        client.put("/v1/habit/today", headers=andi, json={"item_id": item_id, "done": True})
    score = client.get("/v1/habit/consistency", headers=andi).json()
    assert len(score["days"]) == 7
    assert score["days"][-1]["completed_count"] == 4  # today is the last entry
    assert 0 <= score["average_percent"] <= 100


# ---- Phase 3 HTTP contract ----
def test_member_lp_post_is_410_gone(client):
    andi = login(client, "andi@example.test", "andi-pass-123")
    assert client.post("/v1/lp", headers=andi, json={"points": 150}).status_code == 410


def test_non_admin_cannot_use_admin_routes(client):
    andi = login(client, "andi@example.test", "andi-pass-123")
    r = client.post("/v1/admin/transactions", headers=andi, json={
        "member_email": "andi@example.test", "transaction_id": "H1", "tx_type": "NEW_PARTNER",
        "lp": 150, "verified_at": "2026-11-20T10:00:00+07:00"})
    assert r.status_code == 403


def test_admin_seed_path_visible_in_member_summary(client):
    _admin_seed_lp(client, "andi@example.test", 150)
    andi = login(client, "andi@example.test", "andi-pass-123")
    assert client.get("/v1/lp/summary", headers=andi).json()["total_lp"] == 150


def test_admin_route_requires_token(client):
    assert client.post("/v1/admin/transactions/import-csv", json={"csv": "x"}).status_code == 401


def test_gep_eligibility_uses_three_new_videos_rule(client):
    andi = login(client, "andi@example.test", "andi-pass-123")
    r = client.get("/v1/gep/eligibility", headers=andi).json()
    assert r["rule"] == "3_new_completed_videos_per_cycle"
    assert r["required_total"] == 3 and r["eligible"] is False
