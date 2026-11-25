"""PSI-2 hardening: webhook secret references (secret VALUES are never stored in the database).

Only a reference such as env:PSI_SRC_ABC_K1 is stored. The value is resolved at runtime by a resolver
(production: environment or a secrets manager; tests: an in-memory dict).
"""
from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from app.models.core import Base, _now
from app.models.psi_source import _new_id


class PspSourceSecret(Base):
    __tablename__ = "psi_source_secrets"
    __table_args__ = (UniqueConstraint("source_id", "kid", name="uq_psi_secret_source_kid"),)

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_new_id)
    source_id: Mapped[str] = mapped_column(ForeignKey("psi_sources.id"), index=True)
    kid: Mapped[str] = mapped_column(String(32))
    secret_ref: Mapped[str] = mapped_column(String(160))  # reference only, e.g. env:NAME
    status: Mapped[str] = mapped_column(String(12))  # PENDING | ACTIVE | RETIRED | REVOKED
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now)
    activated_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    retired_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    revoked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
