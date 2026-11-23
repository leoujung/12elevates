"""Phase 2 service: Golden Elevate Pool LP tracking.

Rules enforced here (same pattern as prospects.py):
- Every read/write is scoped to the owning member.
- LP entries are manually recorded by the member (no automatic 4Life/MyShop integration
  exists). This is a progress-bar milestone tracker, not the coupon/lottery system shown
  in the Golden Elevate Pool mockups -- that is a separate, not-yet-built feature that
  needs its own business-rule confirmation (allocation, draw mechanism) before building.
"""
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.core import LpEntry

GOLDEN_ELEVATE_POOL_TARGET_LP = 150


def record_lp(db: Session, *, owner_member_id: str, points: int, note: str | None = None) -> LpEntry:
    if points <= 0:
        raise ValueError("points must be positive")
    entry = LpEntry(owner_member_id=owner_member_id, points=points, note=note)
    db.add(entry)
    db.commit()
    return entry


def lp_summary_for_member(db: Session, *, member_id: str) -> dict:
    """Total LP recorded and progress toward the 150 LP Golden Elevate Pool milestone."""
    # Phase 3: LP comes only from administrator-verified transactions (gp_transactions).
    # Self-reported LP entries in lp_entries are no longer counted.
    from app.models.gold_pool import GpTransaction
    stmt = select(GpTransaction).where(GpTransaction.owner_member_id == member_id,
                                       GpTransaction.verified_at.is_not(None)).order_by(GpTransaction.verified_at)
    entries = list(db.execute(stmt).scalars())
    total = sum(e.lp for e in entries)
    pct = min(100, round(total / GOLDEN_ELEVATE_POOL_TARGET_LP * 100)) if GOLDEN_ELEVATE_POOL_TARGET_LP else 0
    return {
        "total_lp": total,
        "target_lp": GOLDEN_ELEVATE_POOL_TARGET_LP,
        "percent": pct,
        "qualified": total >= GOLDEN_ELEVATE_POOL_TARGET_LP,
        "entry_count": len(entries),
    }
