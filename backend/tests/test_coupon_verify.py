"""Tests for admin coupon verification (ISSUED -> VERIFIED)."""
import uuid

import pytest
from sqlalchemy import select

from app.models.gold_pool import GpAuditLog, GpCoupon
from app.services import gold_pool_issuance as iss
from app.services import gold_pool_verify as ver
from tests.test_gold_pool_issuance import admin_db  # noqa: F401  (same seeded org, admin, member andi)


def _issued_coupon(admin_db, email="andi@example.test", tx="TX-VERIFY-1"):
    iss.record_manual(admin_db, actor_id="admin-x", member_email=email, transaction_id=tx,
                      tx_type="NEW_PARTNER", lp=150, verified_at="2026-11-20T10:00:00+07:00")
    return admin_db.execute(select(GpCoupon).where(GpCoupon.status == "ISSUED")).scalars().one()


def test_verify_moves_issued_to_verified_and_logs_it(admin_db):
    coupon = _issued_coupon(admin_db)
    ver.verify_coupon(admin_db, coupon_id=coupon.id, actor_id="admin-x", reason="bukti transfer dicek")
    admin_db.refresh(coupon)
    assert coupon.status == "VERIFIED"
    log = admin_db.execute(select(GpAuditLog).where(GpAuditLog.action == "COUPON_VERIFIED")).scalars().one()
    assert (log.before_value, log.after_value, log.reason) == ("ISSUED", "VERIFIED", "bukti transfer dicek")


def test_verify_twice_is_rejected(admin_db):
    coupon = _issued_coupon(admin_db, tx="TX-VERIFY-2")
    ver.verify_coupon(admin_db, coupon_id=coupon.id, actor_id="admin-x", reason="ok")
    with pytest.raises(ver.CouponNotVerifiable) as exc:
        ver.verify_coupon(admin_db, coupon_id=coupon.id, actor_id="admin-x", reason="again")
    assert exc.value.current_status == "VERIFIED"


def test_verify_unknown_coupon_is_not_found(admin_db):
    with pytest.raises(ver.CouponNotFound):
        ver.verify_coupon(admin_db, coupon_id=str(uuid.uuid4()), actor_id="admin-x", reason="x")


def test_verify_requires_a_reason(admin_db):
    coupon = _issued_coupon(admin_db, tx="TX-VERIFY-3")
    with pytest.raises(ValueError):
        ver.verify_coupon(admin_db, coupon_id=coupon.id, actor_id="admin-x", reason="   ")
    admin_db.refresh(coupon)
    assert coupon.status == "ISSUED"  # nothing changed on a rejected request
