"""PSI-2 ingestion tables: idempotency ledger and prospect provenance.

Stores hashes and reason codes only. Raw personal data from rejected events is never persisted.
"""
from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from app.models.core import Base
from app.models.psi_source import _new_id


class PspIngestionEvent(Base):
    __tablename__ = "psi_ingestion_events"
    __table_args__ = (UniqueConstraint("source_id", "idempotency_key", name="uq_psi_event_source_key"),)

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_new_id)
    source_id: Mapped[str] = mapped_column(ForeignKey("psi_sources.id"), index=True)
    idempotency_key: Mapped[str] = mapped_column(String(64))
    payload_hash: Mapped[str] = mapped_column(String(64))
    # RECEIVED (intent committed, outcome unknown) | ACCEPTED | REJECTED | RECONCILE
    # RECONCILE = flagged for operator review; never auto-retried.
    status: Mapped[str] = mapped_column(String(12))
    reason: Mapped[str | None] = mapped_column(String(60), nullable=True)
    prospect_id: Mapped[str | None] = mapped_column(ForeignKey("prospects.id"), nullable=True)
    received_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))


class PspProspectProvenance(Base):
    __tablename__ = "psi_prospect_provenance"
    __table_args__ = (UniqueConstraint("prospect_id", name="uq_psi_provenance_prospect"),)

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_new_id)
    prospect_id: Mapped[str] = mapped_column(ForeignKey("prospects.id"))
    source_id: Mapped[str] = mapped_column(ForeignKey("psi_sources.id"), index=True)
    ingestion_event_id: Mapped[str] = mapped_column(ForeignKey("psi_ingestion_events.id"))
    category: Mapped[str] = mapped_column(String(40))
    collected_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    notice_version: Mapped[str] = mapped_column(String(40))
    purpose: Mapped[str] = mapped_column(String(40))
    evidence_id: Mapped[str | None] = mapped_column(ForeignKey("psi_permission_evidence.id"), nullable=True)
    lawful_basis: Mapped[str | None] = mapped_column(String(24), nullable=True)
