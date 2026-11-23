"""Draw schedule for GOLD ELEVATE POOL (v4 s.6, s.13, s.33).

Safety rules:
- Nothing here executes a draw. Scheduling is informational; the draw engine is not built.
- Draw can only be enabled by an admin AND only when verified coupons >= 30 (v4 s.6).
- Default is DISABLED. Public launch also requires legal review (v4 s.33), tracked as a flag.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime

COLLECTIVE_TARGET = 30


class DrawNotAllowed(Exception):
    def __init__(self, code: str, detail: str = ""):
        super().__init__(code)
        self.code = code
        self.detail = detail


@dataclass
class DrawSchedule:
    enabled: bool = False
    legal_review_approved: bool = False
    scheduled_at: datetime | None = None
    timezone: str = "Asia/Jakarta"
    zoom_url: str | None = None
    notes: list[str] = field(default_factory=list)


def status_for_member(schedule: DrawSchedule, verified_coupons: int) -> dict:
    """Read-only view for members. Never reveals admin-only fields."""
    reasons = []
    if verified_coupons < COLLECTIVE_TARGET:
        reasons.append("COUPON_TARGET_NOT_REACHED")
    if not schedule.legal_review_approved:
        reasons.append("LEGAL_REVIEW_PENDING")
    if not schedule.enabled:
        reasons.append("DRAW_NOT_ENABLED_BY_ADMIN")
    available = not reasons
    return {
        "available": available,
        "verified_coupons": verified_coupons,
        "target": COLLECTIVE_TARGET,
        "scheduled_at": schedule.scheduled_at.isoformat() if schedule.scheduled_at else None,
        "timezone": schedule.timezone,
        # Zoom link shown only when draw is available (v4 s.13: never active before it is published).
        "zoom_url": schedule.zoom_url if available else None,
        "reasons": reasons,
    }


def enable_draw(schedule: DrawSchedule, verified_coupons: int) -> DrawSchedule:
    """Admin action. Refuses below the 30-coupon target and without legal review approval."""
    if verified_coupons < COLLECTIVE_TARGET:
        raise DrawNotAllowed("COUPON_TARGET_NOT_REACHED",
                             f"{verified_coupons}/{COLLECTIVE_TARGET} verified coupons")
    if not schedule.legal_review_approved:
        raise DrawNotAllowed("LEGAL_REVIEW_PENDING", "legal review must be approved first (v4 s.33)")
    if schedule.scheduled_at is None:
        raise DrawNotAllowed("SCHEDULE_REQUIRED", "set date and time before enabling")
    schedule.enabled = True
    return schedule
