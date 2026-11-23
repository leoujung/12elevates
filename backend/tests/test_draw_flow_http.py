"""Integration: full draw flow through the HTTP API (Phase 6).

Chain tested end to end:
  admin records transaction -> coupon ISSUED -> admin verifies -> draw gate
  -> admin runs draw -> winner recorded -> prize DRAW_CONFIRMED -> admin marks DELIVERED
Also checks the security rules that must hold along the way:
  member cannot verify, cannot run draw, cannot deliver prize; draw refused without gates;
  one draw per cycle; audit log written for every admin action.
"""
from sqlalchemy import select

from app.models.gold_pool import GpAuditLog, GpCoupon, GpCycle, GpDraw, GpPrize
from app.services.gold_pool_draw import GpDrawSettings
from tests.test_api_phase1 import client, login  # noqa: F401 (pytest fixture)
from tests.test_gp_draw_routes import _seed_admin


def _gate(client, *, enabled, legal):
    s = client.app.state.session_factory()
    try:
        row = s.get(GpDrawSettings, 1) or GpDrawSettings(id=1)
        row.enabled = enabled
        row.legal_review_approved = legal
        s.merge(row)
        s.commit()
    finally:
        s.close()


def test_full_draw_flow_over_http(client):
    _seed_admin(client)
    admin = login(client, "seed-admin@example.test", "admin-pass-789")
    andi = login(client, "andi@example.test", "andi-pass-123")

    # 1) Admin records a qualifying transaction; a coupon is issued (not yet valid).
    r = client.post("/v1/admin/transactions", headers=admin, json={
        "transaction_id": "HTTP-FLOW-1", "member_email": "andi@example.test",
        "tx_type": "NEW_PARTNER", "lp": 150, "verified_at": "2026-11-20T10:00:00+07:00"})
    assert r.status_code == 201, r.text

    s = client.app.state.session_factory()
    try:
        coupon = s.execute(select(GpCoupon).where(GpCoupon.status == "ISSUED")).scalars().first()
        assert coupon is not None
        coupon_id = coupon.id
    finally:
        s.close()

    # 2) Member cannot verify a coupon (403).
    assert client.post(f"/v1/admin/gp/coupons/{coupon_id}/verify", headers=andi,
                       json={"reason": "saya sendiri"}).status_code == 403

    # 3) Admin verifies with a reason.
    r = client.post(f"/v1/admin/gp/coupons/{coupon_id}/verify", headers=admin, json={"reason": "bukti dicek"})
    assert r.status_code == 200, r.text

    # 4) Draw refused while gate is closed; member cannot run it either.
    _gate(client, enabled=False, legal=True)
    cycle_id = _cycle_id(client)
    r = client.post(f"/v1/admin/gp/cycles/{cycle_id}/run-draw", headers=admin)
    assert r.status_code == 409 and r.json()["detail"]["code"] == "DRAW_NOT_ENABLED"
    assert client.post(f"/v1/admin/gp/cycles/{cycle_id}/run-draw", headers=andi).status_code == 403

    # 5) Gate open -> admin runs draw -> one winner.
    _gate(client, enabled=True, legal=True)
    r = client.post(f"/v1/admin/gp/cycles/{cycle_id}/run-draw", headers=admin)
    assert r.status_code == 200, r.text
    assert r.json()["winning_member_id"]

    # 6) Second run on the same cycle refused.
    r = client.post(f"/v1/admin/gp/cycles/{cycle_id}/run-draw", headers=admin)
    assert r.status_code == 409 and r.json()["detail"]["code"] == "DRAW_ALREADY_EXECUTED"

    # 7) Prize is DRAW_CONFIRMED; member cannot deliver it; admin can, with a note.
    s = client.app.state.session_factory()
    try:
        prize = s.execute(select(GpPrize)).scalars().one()
        prize_id = prize.id
        assert prize.prize_status == "DRAW_CONFIRMED"
        assert s.execute(select(GpDraw)).scalars().all().__len__() == 1
    finally:
        s.close()
    assert client.post(f"/v1/admin/gp/prizes/{prize_id}/deliver", headers=andi,
                       json={"reason": "saya"}).status_code == 403
    r = client.post(f"/v1/admin/gp/prizes/{prize_id}/deliver", headers=admin, json={"reason": "serah terima"})
    assert r.status_code == 200 and r.json()["prize_status"] == "DELIVERED"

    # 8) Audit trail covers every admin action in the flow.
    s = client.app.state.session_factory()
    try:
        actions = {a.action for a in s.execute(select(GpAuditLog)).scalars().all()}
    finally:
        s.close()
    assert {"COUPON_VERIFIED", "DRAW_EXECUTED", "PRIZE_DELIVERED"} <= actions

    # Restore the safe default: draw closed again.
    _gate(client, enabled=False, legal=False)


def _cycle_id(client):
    s = client.app.state.session_factory()
    try:
        return s.execute(select(GpCycle.id)).scalars().first()
    finally:
        s.close()
