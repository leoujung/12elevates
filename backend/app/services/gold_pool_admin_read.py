"""Admin read endpoints for Phase 4 (cycles, pending coupons, prizes, audit log).

Read-only by design. Writes stay on the already-tested endpoints
(coupon verify, draw settings). All require is_admin (require_admin).
"""
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.models.gold_pool import GpAuditLog, GpCoupon, GpCycle, GpPrize
from app.services import gold_pool_rules as rules


def list_cycles(db: Session) -> dict:
    cycles = db.execute(select(GpCycle).order_by(GpCycle.cycle_number.desc())).scalars().all()
    out = []
    for c in cycles:
        verified = db.execute(select(func.count()).select_from(GpCoupon).where(
            GpCoupon.original_cycle_id == c.id, GpCoupon.status == rules.VERIFIED)).scalar_one()
        issued = db.execute(select(func.count()).select_from(GpCoupon).where(
            GpCoupon.original_cycle_id == c.id, GpCoupon.status == rules.ISSUED)).scalar_one()
        out.append({"cycle_number": c.cycle_number, "status": c.status,
                    "verified_coupons": verified, "waiting_coupons": issued,
                    "target": 30})
    return {"cycles": out}


def pending_coupons(db: Session, limit: int = 200) -> dict:
    rows = db.execute(select(GpCoupon).where(GpCoupon.status == rules.ISSUED)
                      .order_by(GpCoupon.issued_at.asc()).limit(limit)).scalars().all()
    return {"coupons": [{"coupon_id": c.id, "owner_member_id": c.owner_member_id,
                         "lp_at_issue": c.lp_at_issue,
                         "issued_at": c.issued_at.isoformat() if c.issued_at else None}
                        for c in rows]}


def prize_list(db: Session) -> dict:
    rows = db.execute(select(GpPrize).limit(500)).scalars().all()
    return {"prizes": [{c.name: getattr(r, c.name) for c in GpPrize.__table__.columns} for r in rows]}


def audit_log(db: Session, limit: int = 100) -> dict:
    rows = db.execute(select(GpAuditLog).order_by(GpAuditLog.at.desc()).limit(limit)).scalars().all()
    return {"entries": [{"at": r.at.isoformat() if r.at else None, "actor_id": r.actor_id,
                         "action": r.action, "entity_type": r.entity_type, "entity_id": r.entity_id,
                         "before": r.before_value, "after": r.after_value, "reason": r.reason}
                        for r in rows]}
