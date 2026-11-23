"""Gold Pool draw schedule: member read-only status + admin scheduling (v4 s.6, s.13, s.33)."""
from __future__ import annotations

from datetime import datetime

from sqlalchemy import Boolean, DateTime, Integer, String, func, select
from sqlalchemy.orm import Mapped, Session, mapped_column

from app.models.core import Base
from app.services.draw_schedule import DrawNotAllowed, DrawSchedule, enable_draw, status_for_member


class GpDrawSettings(Base):
    """Single-row settings for the draw. Default disabled; never executes a draw."""
    __tablename__ = "gp_draw_settings"
    id: Mapped[int] = mapped_column(Integer, primary_key=True, default=1)
    enabled: Mapped[bool] = mapped_column(Boolean, default=False, server_default="false")
    legal_review_approved: Mapped[bool] = mapped_column(Boolean, default=False, server_default="false")
    scheduled_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    timezone: Mapped[str] = mapped_column(String(64), default="Asia/Jakarta")
    zoom_url: Mapped[str | None] = mapped_column(String(512), nullable=True)


def _verified_coupons(db: Session) -> int:
    """Coupons issued from admin-verified transactions. Never counts client input."""
    from app.models.gold_pool import GpCoupon
    return db.execute(select(func.count()).select_from(GpCoupon)).scalar_one()


def _load(db: Session) -> DrawSchedule:
    row = db.get(GpDrawSettings, 1)
    if row is None:
        return DrawSchedule()
    return DrawSchedule(enabled=row.enabled, legal_review_approved=row.legal_review_approved,
                        scheduled_at=row.scheduled_at, timezone=row.timezone, zoom_url=row.zoom_url)


def _save(db: Session, s: DrawSchedule) -> None:
    row = db.get(GpDrawSettings, 1) or GpDrawSettings(id=1)
    row.enabled = s.enabled
    row.legal_review_approved = s.legal_review_approved
    row.scheduled_at = s.scheduled_at
    row.timezone = s.timezone
    row.zoom_url = s.zoom_url
    db.merge(row)
    db.commit()


def member_status(db: Session) -> dict:
    return status_for_member(_load(db), verified_coupons=_verified_coupons(db))


def admin_update(db: Session, *, scheduled_at: datetime | None, zoom_url: str | None,
                 legal_review_approved: bool, timezone_name: str = "Asia/Jakarta") -> dict:
    s = _load(db)
    s.scheduled_at = scheduled_at
    s.zoom_url = zoom_url
    s.legal_review_approved = legal_review_approved
    s.timezone = timezone_name
    _save(db, s)
    return status_for_member(s, verified_coupons=_verified_coupons(db))


def admin_enable(db: Session) -> dict:
    s = _load(db)
    s = enable_draw(s, verified_coupons=_verified_coupons(db))  # raises DrawNotAllowed
    _save(db, s)
    return status_for_member(s, verified_coupons=_verified_coupons(db))


def admin_disable(db: Session) -> dict:
    s = _load(db)
    s.enabled = False
    _save(db, s)
    return status_for_member(s, verified_coupons=_verified_coupons(db))


__all__ = ["DrawNotAllowed", "GpDrawSettings", "member_status", "admin_update", "admin_enable", "admin_disable"]
