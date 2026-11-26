"""PSI-2 hardening: permission evidence table.

evidence.id is the opaque evidence_ref carried by ingestion payloads.
"""
from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, String
from sqlalchemy.orm import Mapped, mapped_column

from app.models.core import Base, _now
from app.models.psi_source import _new_id


class PspPermissionEvidence(Base):
    __tablename__ = "psi_permission_evidence"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_new_id)
    source_id: Mapped[str] = mapped_column(ForeignKey("psi_sources.id"), index=True)
    purpose: Mapped[str] = mapped_column(String(40))
    lawful_basis: Mapped[str] = mapped_column(String(24))
    legal_review_status: Mapped[str] = mapped_column(String(24))
    legal_review_ref: Mapped[str | None] = mapped_column(String(200), nullable=True)
    notice_version: Mapped[str] = mapped_column(String(40))
    collection_method: Mapped[str] = mapped_column(String(40))
    collected_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    valid_until: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    status: Mapped[str] = mapped_column(String(12))  # PENDING | ACTIVE | REVOKED
    recorded_by: Mapped[str | None] = mapped_column(String(36), nullable=True)
    revoked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now)
