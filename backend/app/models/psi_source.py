"""PSI-1 Source Registry: models (Prospect Source Intelligence).

Additive only. Does not alter existing tables (members, prospects, consent_records, audit_logs).
Six canonical categories are a closed set; do not add categories without Director approval.
Synthetic data only during PSI-1. No real prospect personal data is stored here.
"""
import uuid
from datetime import datetime

from sqlalchemy import Boolean, DateTime, ForeignKey, Integer, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from app.models.core import Base, _now


def _new_id() -> str:
    return str(uuid.uuid4())


class PspSource(Base):
    """One prospect source. owner_member_id NULL = central (admin-owned) source."""
    __tablename__ = "psi_sources"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_new_id)
    category: Mapped[str] = mapped_column(String(40), index=True)
    name: Mapped[str] = mapped_column(String(200))
    owner_member_id: Mapped[str | None] = mapped_column(ForeignKey("members.id"), nullable=True, index=True)
    status: Mapped[str] = mapped_column(String(20), default="DRAFT", index=True)
    approved_by: Mapped[str | None] = mapped_column(String(36), nullable=True)
    approved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    legal_record_ref: Mapped[str | None] = mapped_column(String(200), nullable=True)
    revoked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now)


class PspSourcePermissionProfile(Base):
    """Authorization metadata for one source. Exactly one profile per source."""
    __tablename__ = "psi_source_permission_profiles"
    __table_args__ = (UniqueConstraint("source_id", name="uq_psi_profile_source"),)

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_new_id)
    source_id: Mapped[str] = mapped_column(ForeignKey("psi_sources.id"), index=True)
    data_sharing_scope: Mapped[str] = mapped_column(String(40), default="NONE")
    permitted_fields: Mapped[str] = mapped_column(Text, default="")
    permitted_purposes: Mapped[str] = mapped_column(Text, default="")
    terms_ref: Mapped[str | None] = mapped_column(String(200), nullable=True)
    expires_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now)


class PspSourceAuditEvent(Base):
    """Append-only source audit trail. outcome records allowed AND refused attempts."""
    __tablename__ = "psi_source_audit_events"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_new_id)
    source_id: Mapped[str | None] = mapped_column(String(36), nullable=True, index=True)
    actor_member_id: Mapped[str | None] = mapped_column(String(36), nullable=True)
    action: Mapped[str] = mapped_column(String(60))
    outcome: Mapped[str] = mapped_column(String(10))  # ALLOWED | REFUSED
    detail: Mapped[str | None] = mapped_column(String(300), nullable=True)
    at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now)
