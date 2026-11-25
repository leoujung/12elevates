"""PSI-1 Source Registry tables (psi_sources, psi_source_permission_profiles, psi_source_audit_events).

Additive only. Does NOT touch members, prospects, consent_records, audit_logs, or gp_* tables.
Parent: 2164293a3447 (origin/main migration head, isolated PSI branch).
The unverified suppression migration (e5f6gp05suppression, scratch only) is intentionally NOT
included: its schema is not yet verified against production (see recovery audit).
"""
from alembic import op
import sqlalchemy as sa

revision = "f6a7psi01sources"
down_revision = "2164293a3447"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "psi_sources",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("category", sa.String(40), nullable=False),
        sa.Column("name", sa.String(200), nullable=False),
        sa.Column("owner_member_id", sa.String(36), sa.ForeignKey("members.id"), nullable=True),
        sa.Column("status", sa.String(20), nullable=False, server_default="DRAFT"),
        sa.Column("approved_by", sa.String(36), nullable=True),
        sa.Column("approved_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("legal_record_ref", sa.String(200), nullable=True),
        sa.Column("revoked_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index("ix_psi_sources_category", "psi_sources", ["category"])
    op.create_index("ix_psi_sources_owner_member_id", "psi_sources", ["owner_member_id"])
    op.create_index("ix_psi_sources_status", "psi_sources", ["status"])

    op.create_table(
        "psi_source_permission_profiles",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("source_id", sa.String(36), sa.ForeignKey("psi_sources.id"), nullable=False),
        sa.Column("data_sharing_scope", sa.String(40), nullable=False, server_default="NONE"),
        sa.Column("permitted_fields", sa.Text, nullable=False, server_default=""),
        sa.Column("permitted_purposes", sa.Text, nullable=False, server_default=""),
        sa.Column("terms_ref", sa.String(200), nullable=True),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint("source_id", name="uq_psi_profile_source"),
    )
    op.create_index("ix_psi_source_permission_profiles_source_id",
                    "psi_source_permission_profiles", ["source_id"])

    op.create_table(
        "psi_source_audit_events",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("source_id", sa.String(36), nullable=True),
        sa.Column("actor_member_id", sa.String(36), nullable=True),
        sa.Column("action", sa.String(60), nullable=False),
        sa.Column("outcome", sa.String(10), nullable=False),
        sa.Column("detail", sa.String(300), nullable=True),
        sa.Column("at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index("ix_psi_source_audit_events_source_id", "psi_source_audit_events", ["source_id"])


def downgrade():
    op.drop_index("ix_psi_source_audit_events_source_id", table_name="psi_source_audit_events")
    op.drop_table("psi_source_audit_events")
    op.drop_index("ix_psi_source_permission_profiles_source_id",
                  table_name="psi_source_permission_profiles")
    op.drop_table("psi_source_permission_profiles")
    op.drop_index("ix_psi_sources_status", table_name="psi_sources")
    op.drop_index("ix_psi_sources_owner_member_id", table_name="psi_sources")
    op.drop_index("ix_psi_sources_category", table_name="psi_sources")
    op.drop_table("psi_sources")
