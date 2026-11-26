"""Tests: draw target counts only admin-VERIFIED coupons (never ISSUED)."""
from sqlalchemy import select

from app.models.gold_pool import GpCoupon
from app.services import gold_pool_draw as draw
from app.services import gold_pool_issuance as iss


def test_issued_coupons_do_not_count_toward_draw_target(db):
    iss.record_manual(db, actor_id="admin-x", member_email="andi@example.test",
                      transaction_id="TX-DRAW-ISSUED", tx_type="NEW_PARTNER", lp=150,
                      verified_at="2026-11-20T10:00:00+07:00")
    assert db.execute(select(GpCoupon)).scalars().first().status == "ISSUED"
    assert draw._verified_coupons(db) == 0


def test_verified_coupons_count_toward_draw_target(db):
    from app.services import gold_pool_verify as ver
    iss.record_manual(db, actor_id="admin-x", member_email="andi@example.test",
                      transaction_id="TX-DRAW-VER", tx_type="NEW_PARTNER", lp=150,
                      verified_at="2026-11-20T10:00:00+07:00")
    coupon = db.execute(select(GpCoupon)).scalars().first()
    ver.verify_coupon(db, coupon_id=coupon.id, actor_id="admin-x", reason="cek bukti")
    assert draw._verified_coupons(db) == 1
