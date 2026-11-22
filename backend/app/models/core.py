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
    """One row per member per calendar day: how many of the 12 daily habit items were
    completed. The specific 12 items are not modelled yet (not defined by the business
    owner); this stores only a count out of 12 so the UI can show real progress without
    inventing item names."""
    __tablename__ = "habit_days"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    owner_member_id: Mapped[str] = mapped_column(ForeignKey("members.id"), index=True)
    day: Mapped[str] = mapped_column(String(10))  # YYYY-MM-DD, one row per member per day
    completed_count: Mapped[int] = mapped_column(default=0)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now, onupdate=_now)
