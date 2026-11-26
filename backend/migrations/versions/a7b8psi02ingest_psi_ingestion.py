"""PSI-2 ingestion ledger and prospect provenance (psi_ingestion_events, psi_prospect_provenance).

Additive only. Parent: f6a7psi01sources (PSI-1). Does not alter members, prospects, consent_records,
audit_logs, or gp_* tables. Stores hashes and reason codes only.
"""
from alembic import op
import sqlalchemy as sa

revision = "a7b8psi02ingest"
down_revision = "f6a7psi01sources"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "psi_ingestion_events",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("source_id", sa.String(36), sa.ForeignKey("psi_sources.id"), nullable=False),
        sa.Column("idempotency_key", sa.String(64), nullable=False),
        sa.Column("payload_hash", sa.String(64), nullable=False),
        sa.Column("status", sa.String(12), nullable=False),
        sa.Column("reason", sa.String(60), nullable=True),
        sa.Column("prospect_id", sa.String(36), sa.ForeignKey("prospects.id"), nullable=True),
        sa.Column("received_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint("source_id", "idempotency_key", name="uq_psi_event_source_key"),
    )
    op.create_index("ix_psi_ingestion_events_source_id", "psi_ingestion_events", ["source_id"])

    op.create_table(
        "psi_prospect_provenance",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("prospect_id", sa.String(36), sa.ForeignKey("prospects.id"), nullable=False),
        sa.Column("source_id", sa.String(36), sa.ForeignKey("psi_sources.id"), nullable=False),
        sa.Column("ingestion_event_id", sa.String(36), sa.ForeignKey("psi_ingestion_events.id"),
                  nullable=False),
        sa.Column("category", sa.String(40), nullable=False),
        sa.Column("collected_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("notice_version", sa.String(40), nullable=False),
        sa.Column("purpose", sa.String(40), nullable=False),
        sa.UniqueConstraint("prospect_id", name="uq_psi_provenance_prospect"),
    )
    op.create_index("ix_psi_prospect_provenance_source_id", "psi_prospect_provenance", ["source_id"])


def downgrade():
    op.drop_index("ix_psi_prospect_provenance_source_id", table_name="psi_prospect_provenance")
    op.drop_table("psi_prospect_provenance")
    op.drop_index("ix_psi_ingestion_events_source_id", table_name="psi_ingestion_events")
    op.drop_table("psi_ingestion_events")
