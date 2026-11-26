"""GOLD ELEVATE POOL business rules (Master System Prompt v4.0).

Pure functions only: no database and no network access. Every rule that decides coupon
issuance, eligibility, or the winner lives here so it can be tested exhaustively.
"""
from __future__ import annotations

import hashlib
import secrets
from collections.abc import Callable, Iterable, Sequence

# --- Official constants (v4 §5-§12) -------------------------------------------------
COLLECTIVE_TARGET = 30
MIN_LP_PER_COUPON = 150
NETWORK_MIN_MEMBERS = 36
MAX_NETWORK_LEVEL = 3
ACADEMY_NEW_VIDEOS_REQUIRED = 3
LIFETIME_DRAW_LIMIT = 10
ELIGIBLE_TX_TYPES = frozenset({"NEW_PARTNER", "LOYALTY_ORDER"})

# --- Coupon statuses (v4 §11.4) -----------------------------------------------------
ISSUED = "ISSUED"
VERIFIED = "VERIFIED"
PENDING_ACADEMY = "PENDING_ACADEMY"
PENDING_NETWORK = "PENDING_NETWORK"
EXCLUDED_COOLDOWN = "EXCLUDED_COOLDOWN"
EXCLUDED_LIFETIME_LIMIT = "EXCLUDED_LIFETIME_LIMIT"
ELIGIBLE = "ELIGIBLE"
SNAPSHOT_LOCKED = "SNAPSHOT_LOCKED"
USED = "USED"
CARRIED_FORWARD = "CARRIED_FORWARD"
VOIDED = "VOIDED"

# Reason codes recorded alongside a status (v4 §21: never hide other failed conditions)
REASON_LIFETIME = "LIFETIME_LIMIT_REACHED"
REASON_COOLDOWN = "WINNER_COOLDOWN"
REASON_NETWORK = "NETWORK_BELOW_36"
REASON_ACADEMY = "ACADEMY_INCOMPLETE"


class AcademyBatchError(ValueError):
    """Raised when fewer than three new, verified, unused Academy videos are supplied."""


class DrawError(Exception):
    """Raised when a draw must be blocked. `code` is a stable machine-readable reason."""

    def __init__(self, code: str):
        super().__init__(code)
        self.code = code


def coupon_count_for_transaction(tx_type: str, lp: int, verified: bool) -> int:
    """One qualifying verified transaction produces at most ONE coupon (v4 §5.1).

    There is no LP multiplier: 400 LP still yields exactly one coupon.
    """
    if not verified or tx_type not in ELIGIBLE_TX_TYPES:
        return 0
    if isinstance(lp, bool) or not isinstance(lp, int):
        return 0
    return 1 if lp >= MIN_LP_PER_COUPON else 0


def collective_progress(count: int) -> dict:
    """Collective target progress. Counts NEW verified coupons allocated to the cycle only (v4 §6)."""
    if count < 0:
        raise ValueError("coupon count cannot be negative")
    return {
        "count": count,
        "target": COLLECTIVE_TARGET,
        "percent": min(100, count * 100 // COLLECTIVE_TARGET),
        "target_reached": count >= COLLECTIVE_TARGET,
    }


def count_network(nodes: Iterable[tuple[str, int]]) -> dict:
    """Count unique members across Level 0-3 (v4 §8).

    Each member is counted once, at their shallowest level. Levels outside 0-3 are ignored.
    `nodes` must come from the server-side genealogy traversal, never from the client.
    """
    best: dict[str, int] = {}
    for member_id, level in nodes:
        if level not in range(MAX_NETWORK_LEVEL + 1):
            continue
        if member_id not in best or level < best[member_id]:
            best[member_id] = level
    by_level = {0: 0, 1: 0, 2: 0, 3: 0}
    for lv in best.values():
        by_level[lv] += 1
    total = len(best)
    return {
        "level0": by_level[0],
        "level1": by_level[1],
        "level2": by_level[2],
        "level3": by_level[3],
        "total": total,
        "qualified": total >= NETWORK_MIN_MEMBERS,
    }


def validate_academy_batch(candidates: Sequence[tuple[str, bool]], already_used: set[str]) -> list[str]:
    """Pick exactly three NEW, backend-verified, not-previously-used videos (v4 §7).

    `candidates` is a sequence of (video_id, verified_completed). Unverified videos,
    videos already consumed in any earlier batch, and duplicates are ignored.
    """
    chosen: list[str] = []
    seen: set[str] = set()
    for video_id, verified in candidates:
        if not verified or video_id in already_used or video_id in seen:
            continue
        seen.add(video_id)
        chosen.append(video_id)
    if len(chosen) < ACADEMY_NEW_VIDEOS_REQUIRED:
        raise AcademyBatchError("ACADEMY_THREE_NEW_VIDEOS_REQUIRED")
    return chosen[:ACADEMY_NEW_VIDEOS_REQUIRED]


def lifetime_participation_count(draw_ids: Iterable[str]) -> int:
    """One participation per distinct draw, regardless of coupon count (v4 §9.2)."""
    return len(set(draw_ids))


def determine_eligibility(
    *,
    coupon_used: bool,
    coupon_voided: bool,
    lifetime_count: int,
    cooldown_active: bool,
    network_ok: bool,
    academy_ok: bool,
) -> tuple[str, list[str]]:
    """Return (status, reasons). Reasons lists EVERY failed condition, not just the first (v4 §21)."""
    if coupon_used:
        return USED, []
    if coupon_voided:
        return VOIDED, []

    reasons: list[str] = []
    if lifetime_count >= LIFETIME_DRAW_LIMIT:
        reasons.append(REASON_LIFETIME)
    if cooldown_active:
        reasons.append(REASON_COOLDOWN)
    if not network_ok:
        reasons.append(REASON_NETWORK)
    if not academy_ok:
        reasons.append(REASON_ACADEMY)

    if lifetime_count >= LIFETIME_DRAW_LIMIT:
        return EXCLUDED_LIFETIME_LIMIT, reasons
    if cooldown_active:
        return EXCLUDED_COOLDOWN, reasons
    if not network_ok:
        return PENDING_NETWORK, reasons
    if not academy_ok:
        return PENDING_ACADEMY, reasons
    return ELIGIBLE, []


def snapshot_hash(entries: Sequence[tuple[str, str]]) -> str:
    """SHA-256 over the ordered (coupon_id, member_id) list. Any change to the snapshot changes the hash."""
    payload = "\n".join(f"{coupon_id}|{member_id}" for coupon_id, member_id in entries)
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def select_winner_index(n: int, rng: Callable[[int], int] | None = None) -> int:
    """Uniform index in [0, n). Production uses `secrets` (CSPRNG). `rng` is for tests only."""
    if n <= 0:
        raise DrawError("NO_ELIGIBLE_DRAW_ENTRIES")
    idx = secrets.randbelow(n) if rng is None else rng(n)
    if isinstance(idx, bool) or not isinstance(idx, int) or not 0 <= idx < n:
        raise DrawError("INVALID_RANDOM_INDEX")
    return idx
