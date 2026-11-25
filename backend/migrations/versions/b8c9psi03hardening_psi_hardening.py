"""PSI-2 hardening tables. Additive only. Parent: a7b8psi02ingest (PSI-2 baseline, commit 7b45fc7).

Creates psi_permission_evidence and psi_source_secrets, and adds evidence_id / lawful_basis to
psi_prospect_provenance. Committed revisions are never edited: this is a new revision.

Does not touch members, prospects, consent_records, audit_logs, or gp_* tables.
"""
from alembic import op
import sqlalchemy as sa

revision = "b8c9psi03hardening"
down_revision = "a7b8psi02ingest"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "psi_permission_evidence",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("source_id", sa.String(36), sa.ForeignKey("psi_sources.id"), nullable=False),
        sa.Column("purpose", sa.String(40), nullable=False),
        sa.Column("lawful_basis", sa.String(24), nullable=False),
        sa.Column("legal_review_status", sa.String(24), nullable=False),
        sa.Column("legal_review_ref", sa.String(200), nullable=True),
        sa.Column("notice_version", sa.String(40), nullable=False),
        sa.Column("collection_method", sa.String(40), nullable=False),
        sa.Column("collected_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("valid_until", sa.DateTime(timezone=True), nullable=True),
        sa.Column("status", sa.String(12), nullable=False),
        sa.Column("recorded_by", sa.String(36), nullable=True),
        sa.Column("revoked_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index("ix_psi_permission_evidence_source_id", "psi_permission_evidence", ["source_id"])

    op.create_table(
        "psi_source_secrets",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("source_id", sa.String(36), sa.ForeignKey("psi_sources.id"), nullable=False),
        sa.Column("kid", sa.String(32), nullable=False),
        sa.Column("secret_ref", sa.String(160), nullable=False),
        sa.Column("status", sa.String(12), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("activated_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("retired_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("revoked_at", sa.DateTime(timezone=True), nullable=True),
        sa.UniqueConstraint("source_id", "kid", name="uq_psi_secret_source_kid"),
    )
    op.create_index("ix_psi_source_secrets_source_id", "psi_source_secrets", ["source_id"])

    op.add_column("psi_prospect_provenance",
                  sa.Column("evidence_id", sa.String(36), sa.ForeignKey("psi_permission_evidence.id"), nullable=True))
    op.add_column("psi_prospect_provenance",
                  sa.Column("lawful_basis", sa.String(24), nullable=True))


def downgrade():
    op.drop_column("psi_prospect_provenance", "lawful_basis")
    op.drop_column("psi_prospect_provenance", "evidence_id")
    op.drop_index("ix_psi_source_secrets_source_id", table_name="psi_source_secrets")
    op.drop_table("psi_source_secrets")
    op.drop_index("ix_psi_permission_evidence_source_id", table_name="psi_permission_evidence")
    op.drop_table("psi_permission_evidence")
