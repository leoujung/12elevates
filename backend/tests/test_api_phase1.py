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

    assert client.post("/v1/lp", headers=andi, json={"points": 50, "note": "pack A"}).status_code == 201
    assert client.post("/v1/lp", headers=andi, json={"points": 100}).status_code == 201
    summary = client.get("/v1/lp/summary", headers=andi).json()
    assert summary["total_lp"] == 150
    assert summary["percent"] == 100
    assert summary["qualified"] is True
    assert summary["entry_count"] == 2


def test_lp_rejects_non_positive_points(client):
    andi = login(client, "andi@example.test", "andi-pass-123")
    assert client.post("/v1/lp", headers=andi, json={"points": 0}).status_code == 422
    assert client.post("/v1/lp", headers=andi, json={"points": -5}).status_code == 422


def test_lp_is_isolated_between_members(client):
    andi = login(client, "andi@example.test", "andi-pass-123")
    budi = login(client, "budi@example.test", "budi-pass-456")
    client.post("/v1/lp", headers=andi, json={"points": 150})
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


def test_academy_overview_requires_auth_and_has_16_placeholder_modules(client):
    assert client.get("/v1/academy/overview").status_code == 401
    andi = login(client, "andi@example.test", "andi-pass-123")
    r = client.get("/v1/academy/overview", headers=andi)
    assert r.status_code == 200
    data = r.json()
    assert data["total"] == 16
    assert len(data["modules"]) == 16
    assert data["completed"] == 0
    assert data["percent"] == 0
    # honesty check: no module claims real content or a completed state
    assert all(m["status"] == "coming_soon" and m["title"] == "Segera Hadir" for m in data["modules"])


def test_course_overview_unknown_category_is_404(client):
    andi = login(client, "andi@example.test", "andi-pass-123")
    assert client.get("/v1/courses/does-not-exist", headers=andi).status_code == 404


def test_course_overview_reports_the_8_supplied_edukasi_produk_videos(client):
    andi = login(client, "andi@example.test", "andi-pass-123")
    r = client.get("/v1/courses/edukasi_produk", headers=andi)
    assert r.status_code == 200
    data = r.json()
    assert data["total"] == 24
    assert data["total_ready"] == 8
    ready = [v for v in data["videos"] if v["ready"]]
    assert [v["youtube_id"] for v in ready] == [
        "mTkq8hK6FLQ", "ir-DR-TtqFc", "6U7WvHJFeCk", "mgWIJuCt1gk",
        "1DYdHcABUyA", "_gwKmJZn1kY", "u1ZB8HcyHiY", "DQqTCQiYbus",
    ]
    assert all(v["watched"] is False for v in ready)
    # the remaining 16 catalog entries still have no link and must honestly say so
    assert all(v["ready"] is False and v["youtube_id"] is None for v in data["videos"][8:])


def test_course_percent_counts_only_watchable_videos(client):
    andi = login(client, "andi@example.test", "andi-pass-123")
    r = client.post("/v1/courses/edukasi_produk/watched", headers=andi, json={"youtube_video_id": "mTkq8hK6FLQ"})
    assert r.status_code == 201
    data = client.get("/v1/courses/edukasi_produk", headers=andi).json()
    assert data["completed"] == 1
    # 1 of 8 watchable videos, not 1 of 24 catalog slots; half-up so it matches the dashboard
    assert data["percent"] == 13
    first = data["videos"][0]
    assert first["watched"] is True


def test_mark_watched_rejects_video_with_no_configured_youtube_id(client):
    andi = login(client, "andi@example.test", "andi-pass-123")
    r = client.post("/v1/courses/edukasi_produk/watched", headers=andi, json={"youtube_video_id": "fakeId123"})
    assert r.status_code == 422


def test_mark_watched_and_gep_eligibility_with_a_configured_video(client, monkeypatch):
    from app.services import video_courses as vc
    # Inject one configured (ready) required video so we can test the real path
    # without inventing a fake catalog of 8 videos.
    fake_catalog = [{"order": 0, "title": "Test Video", "youtube_id": "abc123XYZ", "required_for_pool": True}]
    monkeypatch.setitem(vc.CATALOGS, "keuntungan_mitra", fake_catalog)

    andi = login(client, "andi@example.test", "andi-pass-123")
    before = client.get("/v1/gep/eligibility", headers=andi).json()
    assert before["eligible"] is False
    assert before["required_total"] == 1
    assert before["required_watched"] == 0

    r = client.post("/v1/courses/keuntungan_mitra/watched", headers=andi, json={"youtube_video_id": "abc123XYZ"})
    assert r.status_code == 201

    after = client.get("/v1/gep/eligibility", headers=andi).json()
    assert after["eligible"] is True
    assert after["required_watched"] == 1

    # idempotent: marking the same video watched again does not error or duplicate
    r2 = client.post("/v1/courses/keuntungan_mitra/watched", headers=andi, json={"youtube_video_id": "abc123XYZ"})
    assert r2.status_code == 201
    course = client.get("/v1/courses/keuntungan_mitra", headers=andi).json()
    assert course["completed"] == 1


def test_video_watch_progress_is_isolated_between_members(monkeypatch):
    from app.services import video_courses as vc
    fake_catalog = [{"order": 0, "title": "Test Video", "youtube_id": "abc123XYZ", "required_for_pool": True}]
    monkeypatch.setitem(vc.CATALOGS, "keuntungan_mitra", fake_catalog)

    engine = create_engine("sqlite:///:memory:", connect_args={"check_same_thread": False}, poolclass=StaticPool)
    Base.metadata.create_all(engine)
    Session = sessionmaker(bind=engine)
    s = Session()
    org = Organization(name="test org 2")
    s.add(org); s.flush()
    s.add_all([
        Member(id="m-andi2", organization_id=org.id, email="andi2@example.test",
               display_name="Andi2", password_hash=hash_password("pw-andi2")),
        Member(id="m-budi2", organization_id=org.id, email="budi2@example.test",
               display_name="Budi2", password_hash=hash_password("pw-budi2")),
    ])
    s.commit(); s.close()
    local_client = TestClient(create_app(Session))

    andi = login(local_client, "andi2@example.test", "pw-andi2")
    budi = login(local_client, "budi2@example.test", "pw-budi2")
    local_client.post("/v1/courses/keuntungan_mitra/watched", headers=andi, json={"youtube_video_id": "abc123XYZ"})
    assert local_client.get("/v1/gep/eligibility", headers=andi).json()["eligible"] is True
    assert local_client.get("/v1/gep/eligibility", headers=budi).json()["eligible"] is False
