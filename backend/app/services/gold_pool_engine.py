"""Gold Elevate Pool draw engine (Phase 5, v4 s.21-23, v4.1 s.2.6).

Guarantees enforced here, not in the UI:
- Blocked unless draw is ENABLED by admin AND legal review is approved (v4 s.33).
- The cycle row is locked (SELECT ... FOR UPDATE) so two concurrent runs cannot both proceed.
- One draw per cycle (unique cycle_id on gp_draws; checked before writing).
- Snapshot is built once from ELIGIBLE, VERIFIED coupons and locked with a hash.
- Winner is picked only from the snapshot, using secrets (CSPRNG).
- Every participant gets one participation row; winner gets a cooldown and a prize row.
- Everything happens in one transaction: either the whole draw is recorded or nothing is.
"""
from __future__ import annotations

import uuid
from datetime import datetime, timezone

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.gold_pool import (
    GpAuditLog, GpCoupon, GpCycle, GpDraw, GpDrawEntry, GpDrawSnapshot,
    GpParticipation, GpPrize, GpWinnerCooldown,
)
from app.services.gold_pool_draw import GpDrawSettings  # defined in gold_pool_draw.py
from app.services import gold_pool_rules as rules


class DrawBlocked(Exception):
    def __init__(self, code: str, detail: str = ""):
        super().__init__(code)
        self.code = code
        self.detail = detail


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _check_gates(db: Session) -> None:
    settings = db.get(GpDrawSettings, 1)
    if settings is None or not settings.enabled:
        raise DrawBlocked("DRAW_NOT_ENABLED", "draw is not enabled by admin")
    if not settings.legal_review_approved:
        raise DrawBlocked("LEGAL_REVIEW_PENDING", "legal review must be approved (v4 s.33)")


def _lock_cycle(db: Session, cycle_id: str) -> GpCycle:
    cycle = db.execute(select(GpCycle).where(GpCycle.id == cycle_id).with_for_update()).scalar_one_or_none()
    if cycle is None:
        raise DrawBlocked("CYCLE_NOT_FOUND")
    return cycle


def _existing_draw(db: Session, cycle_id: str) -> GpDraw | None:
    return db.execute(select(GpDraw).where(GpDraw.cycle_id == cycle_id)).scalar_one_or_none()


def build_snapshot(db: Session, *, cycle: GpCycle, actor_id: str) -> tuple[GpDrawSnapshot, list[GpCoupon]]:
    """Lock the entry list: VERIFIED coupons of this cycle, in a fixed order (coupon id)."""
    coupons = db.execute(
        select(GpCoupon).where(GpCoupon.original_cycle_id == cycle.id,
                               GpCoupon.status == rules.VERIFIED)
        .order_by(GpCoupon.id.asc())
    ).scalars().all()
    if not coupons:
        raise DrawBlocked("NO_ELIGIBLE_DRAW_ENTRIES", "no verified coupons in this cycle")

    pairs = [(c.id, c.owner_member_id) for c in coupons]
    snap = GpDrawSnapshot(id=str(uuid.uuid4()), cycle_id=cycle.id,
                          snapshot_hash=rules.snapshot_hash(pairs),
                          entry_count=len(pairs), locked_by=actor_id, locked_at=_now())
    db.add(snap)
    db.flush()
    for pos, (coupon_id, member_id) in enumerate(pairs):
        db.add(GpDrawEntry(id=str(uuid.uuid4()), snapshot_id=snap.id,
                           coupon_id=coupon_id, member_id=member_id, position=pos))
    db.flush()
    return snap, coupons


def run_draw(db: Session, *, cycle_id: str, actor_id: str, rng=None) -> dict:
    """Execute one draw for one cycle. Atomic: commits only at the end, rolls back on any error."""
    _check_gates(db)
    cycle = _lock_cycle(db, cycle_id)
    if _existing_draw(db, cycle.id) is not None:
        raise DrawBlocked("DRAW_ALREADY_EXECUTED", "this cycle already has a draw")

    snap, coupons = build_snapshot(db, cycle=cycle, actor_id=actor_id)
    idx = rules.select_winner_index(len(coupons), rng=rng)
    winner_coupon = coupons[idx]

    draw = GpDraw(id=str(uuid.uuid4()), cycle_id=cycle.id, snapshot_id=snap.id,
                  winning_coupon_id=winner_coupon.id, winning_member_id=winner_coupon.owner_member_id,
                  winning_index=idx, selection_method="CSPRNG_SECRETS_RANDBELOW",
                  executed_by=actor_id, executed_at=_now())
    db.add(draw)
    db.flush()

    # Participation: one row per distinct member in this snapshot (v4 s.9.2).
    members = {c.owner_member_id for c in coupons}
    for member_id in members:
        db.add(GpParticipation(id=str(uuid.uuid4()), member_id=member_id, draw_id=draw.id))

    # Winner: prize row (CONFIRMED, not yet delivered) and cooldown for the next full cycle.
    db.add(GpPrize(id=str(uuid.uuid4()), draw_id=draw.id, winner_member_id=winner_coupon.owner_member_id,
                   prize_status="DRAW_CONFIRMED"))
    db.add(GpWinnerCooldown(id=str(uuid.uuid4()), member_id=winner_coupon.owner_member_id,
                            draw_id=draw.id, excluded_cycle_id=cycle.id, status="ACTIVE"))

    cycle.status = "DRAWN"
    db.add(GpAuditLog(id=str(uuid.uuid4()), actor_id=actor_id, action="DRAW_EXECUTED",
                      entity_type="gp_draws", entity_id=draw.id,
                      before_value="OPEN", after_value=f"DRAWN;snapshot={snap.snapshot_hash[:16]};entries={len(coupons)}",
                      reason=f"cycle #{cycle.cycle_number}", at=_now()))
    db.commit()
    return {"draw_id": draw.id, "cycle_number": cycle.cycle_number, "entries": len(coupons),
            "snapshot_hash": snap.snapshot_hash, "winning_member_id": winner_coupon.owner_member_id}
