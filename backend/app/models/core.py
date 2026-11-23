"""Phase 1 core models: members, organizations, prospects, consent_records, audit_logs.

Source of truth: ARCHITECTURE_MAP_v1.0.md Section 5 (schema) and Section 17 (acceptance).
Health data is intentionally NOT stored here (Addendum 11.3).
"""
import uuid
from datetime import datetime, timezone

from sqlalchemy import DateTime, ForeignKey, String, Boolean
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column


def _now() -> datetime:
    return datetime.now(timezone.utc)


class Base(DeclarativeBase):
    pass


class Organization(Base):
    __tablename__ = "organizations"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    name: Mapped[str] = mapped_column(String(200))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now)


class Member(Base):
    __tablename__ = "members"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    organization_id: Mapped[str] = mapped_column(ForeignKey("organizations.id"), index=True)
    email: Mapped[str] = mapped_column(String(320), unique=True)
    display_name: Mapped[str] = mapped_column(String(200))
    password_hash: Mapped[str | None] = mapped_column(String(100), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now)
    # Phase 3: admin role for Gold Pool transaction import and draw operations. Default off.
    is_admin: Mapped[bool] = mapped_column(Boolean, default=False, server_default="false")
    # Network + registration metadata (nullable; for future network features). Sponsor never shown to other members.
    sponsor_name: Mapped[str | None] = mapped_column(String(200), nullable=True)
    sponsor_ref: Mapped[str | None] = mapped_column(String(100), nullable=True)
    registration_channel: Mapped[str | None] = mapped_column(String(10), nullable=True)


class Prospect(Base):
    """Owned by exactly one member. Every query must filter by owner_member_id."""
    __tablename__ = "prospects"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    owner_member_id: Mapped[str] = mapped_column(ForeignKey("members.id"), index=True)
    name: Mapped[str] = mapped_column(String(200))
    whatsapp: Mapped[str | None] = mapped_column(String(32), nullable=True)
    email: Mapped[str | None] = mapped_column(String(320), nullable=True)
    source: Mapped[str] = mapped_column(String(100))
    status: Mapped[str] = mapped_column(String(32), default="new")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now)


class ConsentRecord(Base):
    __tablename__ = "consent_records"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    prospect_id: Mapped[str] = mapped_column(ForeignKey("prospects.id"), index=True)
    purpose: Mapped[str] = mapped_column(String(100))
    granted: Mapped[bool] = mapped_column(Boolean)
    recorded_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now)


class AuditLog(Base):
    __tablename__ = "audit_logs"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    actor_member_id: Mapped[str | None] = mapped_column(String(36), nullable=True)
    action: Mapped[str] = mapped_column(String(100))
    target: Mapped[str] = mapped_column(String(100))
    at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now)


class LpEntry(Base):
    """A manually-recorded LP (Loyalty Point) transaction toward the Golden Elevate Pool
    milestone (150 LP). No automatic integration with 4Life/MyShop exists; the member
    records this themselves. Owned by exactly one member, same isolation rule as Prospect."""
    __tablename__ = "lp_entries"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    owner_member_id: Mapped[str] = mapped_column(ForeignKey("members.id"), index=True)
    points: Mapped[int] = mapped_column()
    note: Mapped[str | None] = mapped_column(String(300), nullable=True)
    recorded_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now)


class HabitDay(Base):
    """One row per member per calendar day for the 12-Hour Daily Habit Tracker.

    completed_items stores a comma-separated list of item ids (see HABIT_ITEMS in
    app/services/habits.py) that were checked that day, e.g. "1,2,3,4". The 12 items
    are the Core 4 + Power-Ups 8 defined in the 22-Nov Master Brief -- not invented here.

    is_rest_day: if true, this day does not break the streak even with 0 items done
    (Streak Freeze). Quota/period for how many rest days are allowed is an ASSUMPTION
    (1 per calendar month) because the brief did not specify a period -- flagged for
    business-owner confirmation, not silently decided as fact.
    """
    __tablename__ = "habit_days"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    owner_member_id: Mapped[str] = mapped_column(ForeignKey("members.id"), index=True)
    day: Mapped[str] = mapped_column(String(10))  # YYYY-MM-DD, one row per member per day
    completed_items: Mapped[str] = mapped_column(String(100), default="")
    is_rest_day: Mapped[bool] = mapped_column(Boolean, default=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now, onupdate=_now)


class VideoProgress(Base):
    """Tracks whether a member finished watching a given video (by YouTube video id).

    Completion is set only by the frontend's YouTube IFrame API onStateChange -> ENDED
    event (see app/services/video_courses.py for the catalog and the honesty note about
    what 'completed' can and cannot guarantee). Not modelled per-category: category is
    looked up from the static catalog via youtube_video_id.
    """
    __tablename__ = "video_progress"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    owner_member_id: Mapped[str] = mapped_column(ForeignKey("members.id"), index=True)
    youtube_video_id: Mapped[str] = mapped_column(String(32), index=True)
    completed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now)
