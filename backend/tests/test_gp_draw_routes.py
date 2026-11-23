"""Integration: draw schedule endpoints. Nothing here may execute a draw."""
import uuid

from app.core.security import hash_password
from app.models.core import Member
from tests.test_api_phase1 import client, login  # noqa: F401 (pytest fixture)


def _seed_admin(client):
    session = client.app.state.session_factory()
    try:
        if session.query(Member).filter(Member.email == "seed-admin@example.test").first() is None:
            andi = session.query(Member).filter(Member.email == "andi@example.test").one()
            session.add(Member(id=str(uuid.uuid4()), organization_id=andi.organization_id,
                               email="seed-admin@example.test", display_name="Seed Admin", is_admin=True,
                               password_hash=hash_password("admin-pass-789")))
            session.commit()
    finally:
        session.close()


def test_member_sees_disabled_status_by_default(client):
    andi = login(client, "andi@example.test", "andi-pass-123")
    r = client.get("/v1/gp/draw-schedule", headers=andi)
    assert r.status_code == 200
    body = r.json()
    assert body["available"] is False
    assert body["zoom_url"] is None
    assert body["target"] == 30


def test_member_cannot_change_schedule(client):
    andi = login(client, "andi@example.test", "andi-pass-123")
    r = client.put("/v1/admin/gp/draw-schedule", headers=andi,
                   json={"legal_review_approved": True, "zoom_url": "https://zoom.example/x"})
    assert r.status_code == 403


def test_admin_cannot_enable_below_thirty_coupons(client):
    _seed_admin(client)
    admin = login(client, "seed-admin@example.test", "admin-pass-789")
    client.put("/v1/admin/gp/draw-schedule", headers=admin, json={
        "legal_review_approved": True, "zoom_url": "https://zoom.example/x",
        "scheduled_at": "2026-12-15T19:00:00+07:00"})
    r = client.post("/v1/admin/gp/draw-enable", headers=admin)
    assert r.status_code == 409
    assert r.json()["detail"]["code"] == "COUPON_TARGET_NOT_REACHED"
    # and member still sees it as unavailable with no Zoom link
    andi = login(client, "andi@example.test", "andi-pass-123")
    m = client.get("/v1/gp/draw-schedule", headers=andi).json()
    assert m["available"] is False and m["zoom_url"] is None
