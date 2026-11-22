"""Phase 2 service: Golden Elevate Pool (LP entries) and 12-Hour Habit Tracker.

Rules enforced here (same pattern as prospects.py):
- Every read/write is scoped to the owning member.
- LP entries are manually recorded by the member (no automatic 4Life/MyShop integration exists).
- Habit tracker stores only a count out of 12; the specific 12 daily items are not modelled
  (not yet defined by the business owner) -- this deliberately avoids inventing a checklist.
"""
from datetime import date

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.core import HabitDay, LpEntry

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
    stmt = select(LpEntry).where(LpEntry.owner_member_id == member_id).order_by(LpEntry.recorded_at)
    entries = list(db.execute(stmt).scalars())
    total = sum(e.points for e in entries)
    pct = min(100, round(total / GOLDEN_ELEVATE_POOL_TARGET_LP * 100)) if GOLDEN_ELEVATE_POOL_TARGET_LP else 0
    return {
        "total_lp": total,
        "target_lp": GOLDEN_ELEVATE_POOL_TARGET_LP,
        "percent": pct,
        "qualified": total >= GOLDEN_ELEVATE_POOL_TARGET_LP,
        "entry_count": len(entries),
    }


def set_habit_progress(db: Session, *, owner_member_id: str, day: str, completed_count: int) -> HabitDay:
    if not (0 <= completed_count <= 12):
        raise ValueError("completed_count must be between 0 and 12")
    stmt = select(HabitDay).where(HabitDay.owner_member_id == owner_member_id, HabitDay.day == day)
    row = db.execute(stmt).scalar_one_or_none()
    if row is None:
        row = HabitDay(owner_member_id=owner_member_id, day=day, completed_count=completed_count)
        db.add(row)
    else:
        row.completed_count = completed_count
    db.commit()
    return row


def habit_today_for_member(db: Session, *, member_id: str, today: str | None = None) -> dict:
    today = today or date.today().isoformat()
    stmt = select(HabitDay).where(HabitDay.owner_member_id == member_id, HabitDay.day == today)
    row = db.execute(stmt).scalar_one_or_none()
    completed = row.completed_count if row else 0
    return {"day": today, "completed_count": completed, "total": 12}
