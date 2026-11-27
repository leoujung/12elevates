"""NBI: discovery jobs and matching results (schema only, no data).

Revision ID: i2j3nbischema01
Revises: h1i2refcodes01

Schema mirrors staging (elevate_staging, nbi_phase1). Differences, on purpose:
- is_synthetic defaults to FALSE in production (staging used TRUE).
  Demo rows must never be created here; they stay in staging only.
- No data is inserted by this migration.
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = "i2j3nbischema01"
down_revision = "h1i2refcodes01"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "nbi_discovery_jobs",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("member_id", sa.String(64), nullable=False, index=True),
        sa.Column("pathway", sa.String(16), nullable=False),
        sa.Column("source_key", sa.String(64), nullable=False),
        sa.Column("is_synthetic", sa.Boolean(), nullable=False, server_default=sa.text("false")),
        sa.Column("status", sa.String(16), nullable=False, server_default=sa.text("'queued'")),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False,
                  server_default=sa.text("now()")),
        sa.Column("finished_at", sa.DateTime(timezone=True), nullable=True),
        sa.CheckConstraint("pathway IN ('business','customer')", name="nbi_discovery_jobs_pathway_check"),
        sa.CheckConstraint("status IN ('queued','running','done','failed','rejected')",
                           name="nbi_discovery_jobs_status_check"),
    )
    op.create_table(
        "nbi_matching_results",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("job_id", sa.String(36), nullable=False, index=True),
        sa.Column("member_id", sa.String(64), nullable=False, index=True),
        sa.Column("prospect_id", postgresql.UUID(as_uuid=False), nullable=True),
        sa.Column("fit_score", sa.Integer(), nullable=True),
        sa.Column("intent_confidence", sa.Integer(), nullable=True),
        sa.Column("data_confidence", sa.Integer(), nullable=True),
        sa.Column("reason", sa.Text(), nullable=False),
        sa.Column("rules_version", sa.String(32), nullable=False),
        sa.Column("is_synthetic", sa.Boolean(), nullable=False, server_default=sa.text("false")),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False,
                  server_default=sa.text("now()")),
        sa.CheckConstraint("fit_score BETWEEN 0 AND 100", name="nbi_matching_results_fit_score_check"),
        sa.CheckConstraint("intent_confidence BETWEEN 0 AND 100",
                           name="nbi_matching_results_intent_confidence_check"),
        sa.CheckConstraint("data_confidence BETWEEN 0 AND 100",
                           name="nbi_matching_results_data_confidence_check"),
        sa.ForeignKeyConstraint(["job_id"], ["nbi_discovery_jobs.id"],
                                name="nbi_matching_results_job_id_fkey", ondelete="CASCADE"),
    )
    # prospect_id FK to cp_prospects is intentionally NOT added: cp_* tables
    # do not exist in production yet. Add it in a later migration after cp_*.

    # Narrow grants for the API role only (no DELETE/TRUNCATE), mirroring
    # member_referral_codes.
    op.execute("GRANT SELECT, INSERT, UPDATE ON nbi_discovery_jobs, nbi_matching_results TO elevate_app")


def downgrade() -> None:
    op.drop_table("nbi_matching_results")
    op.drop_table("nbi_discovery_jobs")
