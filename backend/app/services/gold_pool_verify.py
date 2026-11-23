"""Admin verification of a coupon: ISSUED -> VERIFIED (v4: only verified coupons count).

Rules enforced here, not in the UI:
- Only a coupon currently in ISSUED can be verified.
- Verification is recorded in gp_audit_logs with before/after values and a reason.
- Locking the row prevents double verification under concurrent admin clicks.
- Never creates a coupon; it only changes the status of an existing one.
"""
from datetime import datetime, timezone

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.gold_pool import GpAuditLog, GpCoupon
from app.services import gold_pool_rules as rules


class CouponNotFound(Exception):
    pass


class CouponNotVerifiable(Exception):
    """Raised when the coupon is not ISSUED (already verified, used, or otherwise)."""

    def __init__(self, current_status: str):
        super().__init__(current_status)
        self.current_status = current_status


def verify_coupon(db: Session, *, coupon_id: str, actor_id: str, reason: str) -> GpCoupon:
    if not reason or not reason.strip():
        raise ValueError("reason is required for coupon verification")
    coupon = db.execute(
        select(GpCoupon).where(GpCoupon.id == coupon_id).with_for_update()
    ).scalar_one_or_none()
    if coupon is None:
        raise CouponNotFound(coupon_id)
    if coupon.status != rules.ISSUED:
        raise CouponNotVerifiable(coupon.status)

    before = coupon.status
    coupon.status = rules.VERIFIED
    # No new column: the verification time is the audit log's `at` (set on insert).
    db.add(GpAuditLog(
        actor_id=actor_id,
        action="COUPON_VERIFIED",
        entity_type="gp_coupons",
        entity_id=coupon.id,
        before_value=before,
        after_value=rules.VERIFIED,
        reason=reason.strip()[:300],
    ))
    db.flush()
    return coupon
