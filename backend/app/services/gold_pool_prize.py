"""Prize fulfillment (Phase 4 follow-up): DRAW_CONFIRMED -> DELIVERED.

Rules enforced in the service, not the UI:
- Only a prize in DRAW_CONFIRMED can be marked DELIVERED. Anything else is refused.
- A delivery note (reason) is required and stored in the audit log.
- The prize row is locked so two admins cannot both mark it delivered.
- Nothing here runs or changes a draw.
"""
from datetime import datetime, timezone

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.gold_pool import GpAuditLog, GpPrize

CONFIRMED = "DRAW_CONFIRMED"
DELIVERED = "DELIVERED"


class PrizeNotFound(Exception):
    pass


class PrizeNotDeliverable(Exception):
    def __init__(self, current_status: str):
        super().__init__(current_status)
        self.current_status = current_status


def mark_delivered(db: Session, *, prize_id: str, actor_id: str, reason: str) -> GpPrize:
    if not reason or not reason.strip():
        raise ValueError("delivery note (reason) is required")
    prize = db.execute(select(GpPrize).where(GpPrize.id == prize_id).with_for_update()).scalar_one_or_none()
    if prize is None:
        raise PrizeNotFound(prize_id)
    if prize.prize_status != CONFIRMED:
        raise PrizeNotDeliverable(prize.prize_status)

    before = prize.prize_status
    prize.prize_status = DELIVERED
    prize.delivered_at = datetime.now(timezone.utc)
    db.add(GpAuditLog(
        actor_id=actor_id,
        action="PRIZE_DELIVERED",
        entity_type="gp_prizes",
        entity_id=prize.id,
        before_value=before,
        after_value=DELIVERED,
        reason=reason.strip()[:300],
    ))
    db.flush()
    return prize
