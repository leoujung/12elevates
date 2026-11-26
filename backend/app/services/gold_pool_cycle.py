"""GOLD ELEVATE POOL Phase 2: cycle engine (Master Prompt v4.0 + Spec v4.1).

Pure functions only. No database, no network. The service layer (later) loads trusted
rows, calls these functions, and persists the results inside one transaction.

Covers:
- Collective target (NEW verified coupons only) vs total draw entries (NEW + carry-forward).
- Carry-forward eligibility (v4.1 §1.2).
- Draw pool construction with equal per-coupon probability (v4.1 §2.4).
- Snapshot build with deterministic order and duplicate protection.
- Winner selection from the complete coupon list (v4.1 §2.5).
- Participation and coupon consumption after a successful draw (v4.1 §3, §4).
"""
from __future__ import annotations

from dataclasses import dataclass
from collections.abc import Callable, Iterable, Sequence

from app.services import gold_pool_rules as rules

NEW = "NEW"
CARRY_FORWARD = "CARRY_FORWARD"


class SnapshotError(Exception):
    """Snapshot cannot be built. `code` is stable and machine-readable."""

    def __init__(self, code: str):
        super().__init__(code)
        self.code = code


@dataclass(frozen=True)
class CouponState:
    coupon_id: str
    member_id: str
    allocation_type: str          # NEW | CARRY_FORWARD
    source_cycle_number: int      # cycle where the coupon was issued
    target_cycle_number: int      # cycle being evaluated
    verified: bool
    used: bool
    voided: bool
    lifetime_draws_completed: int  # completed draw participations for the member
    cooldown_active: bool
    network_ok: bool
    academy_ok: bool


def is_carry_forward_eligible(c: CouponState) -> tuple[bool, list[str]]:
    """v4.1 §1.2. Returns (eligible, reasons). Every failed condition is reported."""
    reasons: list[str] = []
    if not c.verified:
        reasons.append("NOT_VERIFIED")
    if c.used:
        reasons.append("ALREADY_USED")
    if c.voided:
        reasons.append("VOIDED")
    if c.lifetime_draws_completed >= rules.LIFETIME_DRAW_LIMIT:
        reasons.append(rules.REASON_LIFETIME)
    if c.cooldown_active:
        reasons.append(rules.REASON_COOLDOWN)
    if not c.network_ok:
        reasons.append(rules.REASON_NETWORK)
    if not c.academy_ok:
        reasons.append(rules.REASON_ACADEMY)
    if c.allocation_type == CARRY_FORWARD and c.source_cycle_number >= c.target_cycle_number:
        reasons.append("CARRY_FORWARD_SOURCE_NOT_EARLIER")
    return (len(reasons) == 0, reasons)


def collective_progress_for_cycle(coupons: Iterable[CouponState], target_cycle_number: int) -> dict:
    """Collective target counts NEW verified coupons allocated to this cycle only (v4.1 §1.3)."""
    count = sum(
        1 for c in coupons
        if c.allocation_type == NEW and c.target_cycle_number == target_cycle_number and c.verified
    )
    return rules.collective_progress(count)


def draw_metrics(coupons: Iterable[CouponState], target_cycle_number: int) -> dict:
    """Two separate metrics (A: collective progress, B: total draw entries). Never merged."""
    coupons = list(coupons)
    new_count = sum(
        1 for c in coupons
        if c.allocation_type == NEW and c.target_cycle_number == target_cycle_number and c.verified
    )
    carry_count = sum(
        1 for c in coupons
        if c.allocation_type == CARRY_FORWARD and c.target_cycle_number == target_cycle_number
        and is_carry_forward_eligible(c)[0]
    )
    return {
        "collective": rules.collective_progress(new_count),   # A
        "new_entries_candidate": new_count,
        "carry_forward_entries_candidate": carry_count,
        "potential_draw_entries": new_count + carry_count,    # B (before member/coupon gates)
    }


def build_draw_snapshot(
    coupons: Sequence[CouponState],
    target_cycle_number: int,
    collective_target_reached: bool,
) -> list[tuple[str, str]]:
    """Build the ordered (coupon_id, member_id) entry list for a draw.

    Raises SnapshotError if the target is not reached, a coupon appears twice, or no
    entry is eligible. Each coupon is one entry: no per-member deduplication (v4.1 §2.2).
    Order is by coupon_id so the snapshot is reproducible for audit.
    """
    if not collective_target_reached:
        raise SnapshotError("COLLECTIVE_TARGET_NOT_REACHED")

    seen: set[str] = set()
    entries: list[tuple[str, str]] = []
    for c in sorted(coupons, key=lambda x: x.coupon_id):
        if c.target_cycle_number != target_cycle_number:
            continue
        if c.coupon_id in seen:
            raise SnapshotError("DUPLICATE_COUPON_IN_SNAPSHOT")
        seen.add(c.coupon_id)
        if c.allocation_type == NEW and not c.verified:
            continue
        ok, _ = is_carry_forward_eligible(c) if c.allocation_type == CARRY_FORWARD else _new_eligible(c)
        if ok:
            entries.append((c.coupon_id, c.member_id))

    if not entries:
        raise SnapshotError("NO_ELIGIBLE_DRAW_ENTRIES")
    return entries


def _new_eligible(c: CouponState) -> tuple[bool, list[str]]:
    """Same gates as carry-forward, applied to a NEW coupon of the current cycle."""
    reasons: list[str] = []
    if c.used:
        reasons.append("ALREADY_USED")
    if c.voided:
        reasons.append("VOIDED")
    if c.lifetime_draws_completed >= rules.LIFETIME_DRAW_LIMIT:
        reasons.append(rules.REASON_LIFETIME)
    if c.cooldown_active:
        reasons.append(rules.REASON_COOLDOWN)
    if not c.network_ok:
        reasons.append(rules.REASON_NETWORK)
    if not c.academy_ok:
        reasons.append(rules.REASON_ACADEMY)
    return (len(reasons) == 0, reasons)


def select_winner(entries: Sequence[tuple[str, str]], rng: Callable[[int], int] | None = None) -> dict:
    """Uniform selection over the full coupon list (v4.1 §2.5). Never picks a member first."""
    idx = rules.select_winner_index(len(entries), rng=rng)
    coupon_id, member_id = entries[idx]
    return {"winning_index": idx, "winning_coupon_id": coupon_id, "winning_member_id": member_id,
            "entry_count": len(entries)}


def participations_after_draw(entries: Sequence[tuple[str, str]], draw_id: str,
                              already_completed: dict[str, int]) -> dict[str, int]:
    """One participation per unique member in the snapshot (v4.1 §3). Returns new lifetime counts."""
    members = {m for _, m in entries}
    out = dict(already_completed)
    for m in members:
        out[m] = out.get(m, 0) + 1
    return out


def coupons_consumed_by_draw(entries: Sequence[tuple[str, str]]) -> list[str]:
    """Every coupon in the locked snapshot becomes USED (v4.1 §4). Winner and non-winners alike."""
    return [coupon_id for coupon_id, _ in entries]
