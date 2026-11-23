"""GOLD ELEVATE POOL Phase 1 tables (Master Prompt v4.0 §31).

Additive only: these tables reference existing `members` but do not alter any existing table.
"""
import uuid
from datetime import datetime

from sqlalchemy import Boolean, DateTime, ForeignKey, Integer, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from app.models.core import Base, _now


def _new_id() -> str:
    return str(uuid.uuid4())


class GpCycle(Base):
    __tablename__ = "gp_cycles"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_new_id)
    cycle_number: Mapped[int] = mapped_column(Integer, unique=True)
    status: Mapped[str] = mapped_column(String(16), default="OPEN")  # OPEN | DRAWN
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now)


class GpTransaction(Base):
    """Verified qualifying-candidate transaction. transaction_id is the external unique key."""
    __tablename__ = "gp_transactions"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_new_id)
    transaction_id: Mapped[str] = mapped_column(String(64), unique=True)
    owner_member_id: Mapped[str] = mapped_column(ForeignKey("members.id"), index=True)
    tx_type: Mapped[str] = mapped_column(String(24))
    lp: Mapped[int] = mapped_column(Integer)
    source: Mapped[str] = mapped_column(String(24))  # ADMIN_MANUAL | CSV_IMPORT
    recorded_by: Mapped[str | None] = mapped_column(String(36), nullable=True)
    verified_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    recorded_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now)
    coupon_count: Mapped[int] = mapped_column(Integer, default=0)


class GpCoupon(Base):
    __tablename__ = "gp_coupons"
    __table_args__ = (
        # DB-level guarantee: one transaction can never produce two coupons.
        UniqueConstraint("transaction_pk", name="uq_gp_coupon_one_per_transaction"),
    )
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_new_id)
    transaction_pk: Mapped[str] = mapped_column(ForeignKey("gp_transactions.id"))
    owner_member_id: Mapped[str] = mapped_column(ForeignKey("members.id"), index=True)
    original_cycle_id: Mapped[str] = mapped_column(ForeignKey("gp_cycles.id"), index=True)  # issuance cycle
    lp_at_issue: Mapped[int] = mapped_column(Integer)
    status: Mapped[str] = mapped_column(String(32), index=True)
    issued_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now)
    used_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class GpDrawSnapshot(Base):
    """Locked, immutable entry list for one cycle (v4 §22, v4.1 §2.6)."""
    __tablename__ = "gp_draw_snapshots"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_new_id)
    cycle_id: Mapped[str] = mapped_column(ForeignKey("gp_cycles.id"), unique=True)  # one snapshot per cycle
    snapshot_hash: Mapped[str] = mapped_column(String(64))
    entry_count: Mapped[int] = mapped_column(Integer)
    locked_by: Mapped[str] = mapped_column(String(36))
    locked_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now)


class GpCouponAllocation(Base):
    """Per-cycle allocation history. Never overwritten across cycles (v4 §23, v4.1 §1.5)."""
    __tablename__ = "gp_coupon_allocations"
    __table_args__ = (
        # A coupon is allocated to a given target cycle at most once.
        UniqueConstraint("coupon_id", "target_cycle_id", name="uq_gp_alloc_coupon_target_cycle"),
    )
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_new_id)
    coupon_id: Mapped[str] = mapped_column(ForeignKey("gp_coupons.id"), index=True)
    source_cycle_id: Mapped[str | None] = mapped_column(ForeignKey("gp_cycles.id"), nullable=True)
    target_cycle_id: Mapped[str] = mapped_column(ForeignKey("gp_cycles.id"), index=True)
    allocation_type: Mapped[str] = mapped_column(String(16))  # NEW | CARRY_FORWARD
    eligibility_status: Mapped[str] = mapped_column(String(32))
    reasons: Mapped[str | None] = mapped_column(String(255), nullable=True)
    snapshot_id: Mapped[str | None] = mapped_column(ForeignKey("gp_draw_snapshots.id"), nullable=True)
    included_in_snapshot: Mapped[bool] = mapped_column(Boolean, default=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now)


class GpAcademyUsage(Base):
    """A video consumed by a qualification batch. Unique per member: never reusable (v4 §7.3)."""
    __tablename__ = "gp_academy_usage"
    __table_args__ = (UniqueConstraint("member_id", "video_id", name="uq_gp_academy_member_video"),)
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_new_id)
    member_id: Mapped[str] = mapped_column(ForeignKey("members.id"), index=True)
    video_id: Mapped[str] = mapped_column(String(64))
    cycle_id: Mapped[str] = mapped_column(ForeignKey("gp_cycles.id"), index=True)
    verified_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now)


class GpDraw(Base):
    __tablename__ = "gp_draws"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_new_id)
    cycle_id: Mapped[str] = mapped_column(ForeignKey("gp_cycles.id"), unique=True)  # duplicate-execution guard
    snapshot_id: Mapped[str] = mapped_column(ForeignKey("gp_draw_snapshots.id"), unique=True)
    winning_coupon_id: Mapped[str] = mapped_column(ForeignKey("gp_coupons.id"))
    winning_member_id: Mapped[str] = mapped_column(ForeignKey("members.id"))
    winning_index: Mapped[int] = mapped_column(Integer)
    selection_method: Mapped[str] = mapped_column(String(32))  # e.g. CSPRNG_SECRETS_RANDBELOW
    executed_by: Mapped[str] = mapped_column(String(36))
    executed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now)


class GpDrawEntry(Base):
    """One row per coupon in the immutable snapshot, in fixed order."""
    __tablename__ = "gp_draw_entries"
    __table_args__ = (
        UniqueConstraint("snapshot_id", "coupon_id", name="uq_gp_entry_snapshot_coupon"),
        UniqueConstraint("snapshot_id", "position", name="uq_gp_entry_snapshot_position"),
    )
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_new_id)
    snapshot_id: Mapped[str] = mapped_column(ForeignKey("gp_draw_snapshots.id"), index=True)
    coupon_id: Mapped[str] = mapped_column(ForeignKey("gp_coupons.id"))
    member_id: Mapped[str] = mapped_column(ForeignKey("members.id"))
    position: Mapped[int] = mapped_column(Integer)


class GpParticipation(Base):
    """One row per member per completed draw. Lifetime count = number of rows (v4 §18)."""
    __tablename__ = "gp_draw_participations"
    __table_args__ = (UniqueConstraint("member_id", "draw_id", name="uq_gp_participation_member_draw"),)
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_new_id)
    member_id: Mapped[str] = mapped_column(ForeignKey("members.id"), index=True)
    draw_id: Mapped[str] = mapped_column(ForeignKey("gp_draws.id"), index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now)


class GpWinnerCooldown(Base):
    __tablename__ = "gp_winner_cooldowns"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_new_id)
    member_id: Mapped[str] = mapped_column(ForeignKey("members.id"), index=True)
    draw_id: Mapped[str] = mapped_column(ForeignKey("gp_draws.id"), unique=True)
    excluded_cycle_id: Mapped[str] = mapped_column(ForeignKey("gp_cycles.id"))
    status: Mapped[str] = mapped_column(String(16), default="ACTIVE")


class GpPrize(Base):
    __tablename__ = "gp_prizes"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_new_id)
    draw_id: Mapped[str] = mapped_column(ForeignKey("gp_draws.id"), unique=True)
    winner_member_id: Mapped[str] = mapped_column(ForeignKey("members.id"))
    prize_status: Mapped[str] = mapped_column(String(32), default="DRAW_CONFIRMED")
    delivered_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class GpAuditLog(Base):
    __tablename__ = "gp_audit_logs"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_new_id)
    actor_id: Mapped[str | None] = mapped_column(String(36), nullable=True)
    action: Mapped[str] = mapped_column(String(64))
    entity_type: Mapped[str] = mapped_column(String(32))
    entity_id: Mapped[str | None] = mapped_column(String(36), nullable=True)
    before_value: Mapped[str | None] = mapped_column(Text, nullable=True)
    after_value: Mapped[str | None] = mapped_column(Text, nullable=True)
    reason: Mapped[str | None] = mapped_column(String(300), nullable=True)
    at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now)
